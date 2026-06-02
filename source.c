/*
 * Star Wars Timeline Crawler — Canon + Legends
 * ------------------------------------------
 * Fetches both:
 *   https://starwars.fandom.com/wiki/Timeline_of_canon_media
 *   https://starwars.fandom.com/wiki/Timeline_of_Legends_media
 *
 * Stores: starwars_timeline.db
 * Columns: universe | year | type | title | released | progress | completed_at | active
 *
 * Build:
 *   gcc -Wall -O2 -o sw_crawler sw_crawler.c -lcurl -lgumbo -lsqlite3 -lcjson
 * ------------------------------------------
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <curl/curl.h>
#include <gumbo.h>
#include <sqlite3.h>
#include <cjson/cJSON.h>

// ── Constants ──────────────────────────────────────────────────────────────────

#define API_BASE    "https://starwars.fandom.com/api.php" \
                    "?action=parse&prop=text&format=json&disablelimitreport=1&page="
#define PAGE_CANON   "Timeline_of_canon_media"
#define PAGE_LEGENDS "Timeline_of_Legends_media"
#define DB_FILE      "starwars_timeline.db"
#define USER_AGENT   "StarWarsTimelineCrawler/1.0 (academic project)"
#define MAX_TEXT     1024
#define MAX_COLS     8

// ── Memory buffer ──────────────────────────────────────────────────────────────

typedef struct { char *data; size_t size; } MemBuf;

static size_t write_cb(void *ptr, size_t size, size_t nmemb, void *userdata)
{
    size_t  bytes = size * nmemb;
    MemBuf *buf   = (MemBuf *)userdata;
    char   *tmp   = realloc(buf->data, buf->size + bytes + 1);
    if (!tmp) return 0;
    buf->data = tmp;
    memcpy(buf->data + buf->size, ptr, bytes);
    buf->size += bytes;
    buf->data[buf->size] = '\0';
    return bytes;
}

// ── HTTP fetch ─────────────────────────────────────────────────────────────────

static char *fetch_url(const char *url)
{
    CURL   *curl = curl_easy_init();
    MemBuf  buf  = { NULL, 0 };
    if (!curl) { fprintf(stderr, "curl_easy_init failed\n"); return NULL; }

    struct curl_slist *headers = NULL;
    headers = curl_slist_append(headers,
        "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8");

    curl_easy_setopt(curl, CURLOPT_URL,            url);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION,  write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA,      &buf);
    curl_easy_setopt(curl, CURLOPT_USERAGENT,      USER_AGENT);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT,        30L);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER,     headers);

    CURLcode res = curl_easy_perform(curl);
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        fprintf(stderr, "curl error: %s\n", curl_easy_strerror(res));
        free(buf.data);
        return NULL;
    }
    return buf.data;
}

// ── JSON → HTML via cJSON ──────────────────────────────────────────────────────

static char *json_extract_html(const char *json_str)
{
    cJSON *root  = cJSON_Parse(json_str);
    if (!root) {
        fprintf(stderr, "cJSON_Parse failed near: %.40s\n",
                cJSON_GetErrorPtr() ? cJSON_GetErrorPtr() : "?");
        return NULL;
    }
    cJSON *parse = cJSON_GetObjectItemCaseSensitive(root, "parse");
    cJSON *text  = parse ? cJSON_GetObjectItemCaseSensitive(parse, "text") : NULL;
    cJSON *star  = text  ? cJSON_GetObjectItemCaseSensitive(text,  "*")    : NULL;

    if (!cJSON_IsString(star) || !star->valuestring) {
        fprintf(stderr, "json_extract_html: parse.text.* not found\n");
        cJSON_Delete(root);
        return NULL;
    }
    char *html = strdup(star->valuestring);
    cJSON_Delete(root);
    return html;
}

// ── Gumbo helpers ─────────────────────────────────────────────────────────────

static void collect_text(GumboNode *node, char *buf, size_t bufsz)
{
    if (!node) return;
    if (node->type == GUMBO_NODE_TEXT) {
        size_t used = strlen(buf), rem = bufsz - used - 1;
        if (rem > 0) strncat(buf, node->v.text.text, rem);
        return;
    }
    if (node->type != GUMBO_NODE_ELEMENT) return;
    switch (node->v.element.tag) {
        case GUMBO_TAG_SCRIPT: case GUMBO_TAG_STYLE:
        case GUMBO_TAG_NOSCRIPT: case GUMBO_TAG_SUP: return;
        default: break;
    }
    GumboVector *ch = &node->v.element.children;
    for (unsigned i = 0; i < (unsigned)ch->length; i++)
        collect_text(ch->data[i], buf, bufsz);
}

static int count_rows(GumboNode *node)
{
    if (!node || node->type != GUMBO_NODE_ELEMENT) return 0;
    int n = (node->v.element.tag == GUMBO_TAG_TR) ? 1 : 0;
    GumboVector *ch = &node->v.element.children;
    for (unsigned i = 0; i < (unsigned)ch->length; i++)
        n += count_rows(ch->data[i]);
    return n;
}

static int collect_wikitables(GumboNode *node, GumboNode **out, int maxout)
{
    if (!node || node->type != GUMBO_NODE_ELEMENT || maxout <= 0) return 0;
    int n = 0;
    if (node->v.element.tag == GUMBO_TAG_TABLE) {
        GumboAttribute *cls =
            gumbo_get_attribute(&node->v.element.attributes, "class");
        if (cls && strstr(cls->value, "wikitable")) {
            out[n++] = node;
            return n;
        }
    }
    GumboVector *ch = &node->v.element.children;
    for (unsigned i = 0; i < (unsigned)ch->length && n < maxout; i++)
        n += collect_wikitables(ch->data[i], out + n, maxout - n);
    return n;
}



// ── String helpers ─────────────────────────────────────────────────────────────

static char *trim(char *s)
{
    while (*s == ' ' || *s == '\t' || *s == '\n' || *s == '\r') s++;
    char *end = s + strlen(s);
    while (end > s && (*(end-1)==' '||*(end-1)=='\t'||
                       *(end-1)=='\n'||*(end-1)=='\r'))
        *(--end) = '\0';
    return s;
}

static void strip_footnotes(const char *src, char *dst, size_t dstsz)
{
    size_t di = 0;
    for (const char *p = src; *p && di < dstsz - 1; p++) {
        if (*p == '[') { while (*p && *p != ']') p++; }
        else dst[di++] = *p;
    }
    dst[di] = '\0';
}

// ── SQLite ─────────────────────────────────────────────────────────────────────

static sqlite3 *open_db(void)
{
    sqlite3 *db;
    if (sqlite3_open(DB_FILE, &db) != SQLITE_OK) {
        fprintf(stderr, "sqlite3_open: %s\n", sqlite3_errmsg(db));
        sqlite3_close(db);
        return NULL;
    }

    /*
     * UNIQUE is now (title, universe) so the same title can exist in both
     * Canon and Legends without conflict.
     * progress and completed_at are tracked per-universe independently.
     */
    const char *ddl =
        "CREATE TABLE IF NOT EXISTS timeline ("
        "  id           INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  universe     TEXT    DEFAULT 'canon',"
        "  year         TEXT,"
        "  type         TEXT,"
        "  title        TEXT,"
        "  released     TEXT,"
        "  progress     TEXT    DEFAULT '',"
        "  completed_at TEXT    DEFAULT NULL,"
        "  active       INTEGER DEFAULT 1,"
        "  UNIQUE(title, universe)"
        ");";

    char *err = NULL;
    if (sqlite3_exec(db, ddl, NULL, NULL, &err) != SQLITE_OK) {
        fprintf(stderr, "DDL error: %s\n", err);
        sqlite3_free(err);
        sqlite3_close(db);
        return NULL;
    }

    /* Safe migrations for older DBs */
    sqlite3_exec(db, "ALTER TABLE timeline ADD COLUMN universe     TEXT    DEFAULT 'canon';", NULL, NULL, NULL);
    sqlite3_exec(db, "ALTER TABLE timeline ADD COLUMN completed_at TEXT    DEFAULT NULL;",    NULL, NULL, NULL);
    sqlite3_exec(db, "ALTER TABLE timeline ADD COLUMN active       INTEGER DEFAULT 1;",       NULL, NULL, NULL);

    /* Soft-delete all rows for this run; upsert will restore active ones */
    sqlite3_exec(db, "UPDATE timeline SET active = 0;", NULL, NULL, NULL);

    return db;
}

// ── Table carry-forward types ──────────────────────────────────────────────────

typedef struct { char text[MAX_TEXT]; int remaining; } ColCarry;
typedef struct { char text[MAX_TEXT]; int rowspan; int colspan; } ActualCell;

static int collect_cells(GumboNode *row, ActualCell *cells, int maxcells)
{
    int n = 0;
    GumboVector *ch = &row->v.element.children;
    for (unsigned ci = 0; ci < (unsigned)ch->length && n < maxcells; ci++) {
        GumboNode *cell = ch->data[ci];
        if (cell->type != GUMBO_NODE_ELEMENT) continue;
        GumboTag tag = cell->v.element.tag;
        if (tag != GUMBO_TAG_TD && tag != GUMBO_TAG_TH) continue;

        char raw[MAX_TEXT] = "";
        collect_text(cell, raw, MAX_TEXT);
        strip_footnotes(raw, cells[n].text, MAX_TEXT);
        char *t = trim(cells[n].text);
        if (t != cells[n].text) memmove(cells[n].text, t, strlen(t) + 1);

        GumboAttribute *rs = gumbo_get_attribute(&cell->v.element.attributes, "rowspan");
        GumboAttribute *cs = gumbo_get_attribute(&cell->v.element.attributes, "colspan");
        cells[n].rowspan = rs ? atoi(rs->value) : 1;
        cells[n].colspan = cs ? atoi(cs->value) : 1;
        if (cells[n].rowspan < 1) cells[n].rowspan = 1;
        if (cells[n].colspan < 1) cells[n].colspan = 1;
        n++;
    }
    return n;
}

static void build_virtual_row(ColCarry *carry, int ncols,
                              ActualCell *actual, int nactual,
                              char vrow[][MAX_TEXT])
{
    int ai = 0;
    for (int col = 0; col < ncols; col++) {
        if (carry[col].remaining > 0) {
            memcpy(vrow[col], carry[col].text, MAX_TEXT);
            carry[col].remaining--;
        } else if (ai < nactual) {
            memcpy(vrow[col], actual[ai].text, MAX_TEXT);
            if (actual[ai].rowspan > 1) {
                memcpy(carry[col].text, actual[ai].text, MAX_TEXT);
                carry[col].remaining = actual[ai].rowspan - 1;
            } else {
                carry[col].remaining = 0;
            }
            int cs = actual[ai].colspan;
            ai++;
            for (int extra = 1; extra < cs && col + extra < ncols; extra++) {
                strncpy(vrow[col + extra], vrow[col], MAX_TEXT - 1);
                carry[col + extra].remaining = 0;
            }
            col += (cs - 1);
        } else {
            vrow[col][0] = '\0';
        }
    }
}

// ── Parse + insert one table ───────────────────────────────────────────────────

static int parse_and_insert(GumboNode *table_node, sqlite3 *db,
                            const char *universe)
{
    const char *sql =
        "INSERT INTO timeline (universe, year, type, title, released, active) "
        "VALUES (?, ?, ?, ?, ?, 1) "
        "ON CONFLICT(title, universe) DO UPDATE SET "
        "  year     = excluded.year,"
        "  type     = excluded.type,"
        "  released = excluded.released,"
        "  active   = 1;";

    sqlite3_stmt *stmt;
    if (sqlite3_prepare_v2(db, sql, -1, &stmt, NULL) != SQLITE_OK) {
        fprintf(stderr, "prepare: %s\n", sqlite3_errmsg(db));
        return -1;
    }

    sqlite3_exec(db, "BEGIN;", NULL, NULL, NULL);

    ColCarry carry[MAX_COLS];
    memset(carry, 0, sizeof(carry));
    bool first_row = true;
    int  inserted  = 0;

    GumboVector *tbl_ch = &table_node->v.element.children;
    for (unsigned ti = 0; ti < (unsigned)tbl_ch->length; ti++) {
        GumboNode *sect = tbl_ch->data[ti];
        if (sect->type != GUMBO_NODE_ELEMENT) continue;

        GumboVector *rows_vec   = NULL;
        GumboNode   *single_row = NULL;

        switch (sect->v.element.tag) {
            case GUMBO_TAG_THEAD:
            case GUMBO_TAG_TBODY: rows_vec   = &sect->v.element.children; break;
            case GUMBO_TAG_TR:    single_row = sect;                       break;
            default: continue;
        }

        unsigned row_count = rows_vec ? (unsigned)rows_vec->length : 1;
        for (unsigned ri = 0; ri < row_count; ri++) {
            GumboNode *row = rows_vec ? rows_vec->data[ri] : single_row;
            if (!row || row->type != GUMBO_NODE_ELEMENT) continue;
            if (row->v.element.tag != GUMBO_TAG_TR) continue;

            ActualCell actual[MAX_COLS];
            int nactual = collect_cells(row, actual, MAX_COLS);
            if (nactual == 0) continue;
            if (first_row) { first_row = false; continue; }

            char vrow[MAX_COLS][MAX_TEXT];
            memset(vrow, 0, sizeof(vrow));
            build_virtual_row(carry, MAX_COLS, actual, nactual, vrow);

            const char *year     = vrow[0];
            const char *type     = vrow[1];
            const char *title    = vrow[2];
            const char *released = vrow[3];

            if (strlen(title) == 0) continue;

            sqlite3_bind_text(stmt, 1, universe, -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 2, year,     -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 3, type,     -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 4, title,    -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 5, released, -1, SQLITE_TRANSIENT);

            if (sqlite3_step(stmt) != SQLITE_DONE)
                fprintf(stderr, "insert: %s\n",
                        sqlite3_errmsg(sqlite3_db_handle(stmt)));

            sqlite3_reset(stmt);
            sqlite3_clear_bindings(stmt);
            inserted++;
        }
    }

    sqlite3_exec(db, "COMMIT;", NULL, NULL, NULL);
    sqlite3_finalize(stmt);
    return inserted;
}

// ── Crawl one source ───────────────────────────────────────────────────────────

static int crawl_source(sqlite3 *db, const char *page, const char *universe)
{
    printf("\n── %s (%s) ────────────────────────────────────\n", page, universe);

    char url[512];
    snprintf(url, sizeof(url), "%s%s", API_BASE, page);

    printf("  [1/3] Fetching...\n");
    char *json = fetch_url(url);
    if (!json) return -1;
    printf("        %zu bytes of JSON.\n", strlen(json));

    char *html = json_extract_html(json);
    free(json);
    if (!html) { fprintf(stderr, "  ERROR: could not extract HTML.\n"); return -1; }
    printf("        %zu bytes of HTML.\n", strlen(html));

    printf("  [2/3] Parsing HTML...\n");
    GumboOutput *output = gumbo_parse(html);

    printf("  [3/3] Finding wikitables...\n");
    GumboNode *tables[64];                                    // bump ceiling
    int ntables = collect_wikitables(output->root, tables, 64);
    if (ntables == 0) {
        fprintf(stderr, "  ERROR: no wikitable found.\n");
        gumbo_destroy_output(&kGumboDefaultOptions, output);
        free(html);
        return -1;
    }
    printf("         Found %d wikitable(s) — processing all.\n", ntables);

    int n = 0;
    for (int t = 0; t < ntables; t++) {
        int rows = count_rows(tables[t]);
        printf("         Table %d/%d: %d rows\n", t + 1, ntables, rows);
        int added = parse_and_insert(tables[t], db, universe);
        if (added >= 0) n += added;
    }
}

// ── main ──────────────────────────────────────────────────────────────────────

int main(void)
{
    printf("=== Star Wars Timeline Crawler (Canon + Legends) ===\n");
    printf("Output: %s\n", DB_FILE);

    sqlite3 *db = open_db();
    if (!db) return EXIT_FAILURE;

    struct { const char *page; const char *universe; } sources[] = {
        { PAGE_CANON,   "canon"   },
        { PAGE_LEGENDS, "legends" },
    };

    int total = 0;
    for (size_t i = 0; i < sizeof(sources)/sizeof(sources[0]); i++) {
        int n = crawl_source(db, sources[i].page, sources[i].universe);
        if (n < 0) {
            fprintf(stderr, "\nWARNING: crawl failed for %s — skipping.\n",
                    sources[i].universe);
        } else {
            total += n;
        }
    }

    /* Soft-delete report */
    sqlite3_stmt *s;
    sqlite3_prepare_v2(db,
        "SELECT universe, COUNT(*) FROM timeline WHERE active=0 GROUP BY universe;",
        -1, &s, NULL);
    bool any_inactive = false;
    while (sqlite3_step(s) == SQLITE_ROW) {
        if (!any_inactive) { printf("\n"); any_inactive = true; }
        printf("  ⚠  %d %s row(s) soft-deleted (no longer on wiki).\n",
               sqlite3_column_int(s, 1),
               sqlite3_column_text(s, 0));
    }
    sqlite3_finalize(s);

    printf("\n✓  Total rows processed: %d\n", total);
    printf("   Columns: universe, year, type, title, released, progress, completed_at, active\n");

    /* Preview */
    printf("\n── First 5 Canon rows ───────────────────────────────────────\n");
    sqlite3_prepare_v2(db,
        "SELECT year, type, title, released FROM timeline "
        "WHERE active=1 AND universe='canon' LIMIT 5;",
        -1, &s, NULL);
    while (sqlite3_step(s) == SQLITE_ROW)
        printf("  [%-20s] %-3s  %-50s  %s\n",
               sqlite3_column_text(s,0), sqlite3_column_text(s,1),
               sqlite3_column_text(s,2), sqlite3_column_text(s,3));
    sqlite3_finalize(s);

    printf("\n── First 5 Legends rows ─────────────────────────────────────\n");
    sqlite3_prepare_v2(db,
        "SELECT year, type, title, released FROM timeline "
        "WHERE active=1 AND universe='legends' LIMIT 5;",
        -1, &s, NULL);
    while (sqlite3_step(s) == SQLITE_ROW)
        printf("  [%-20s] %-3s  %-50s  %s\n",
               sqlite3_column_text(s,0), sqlite3_column_text(s,1),
               sqlite3_column_text(s,2), sqlite3_column_text(s,3));
    sqlite3_finalize(s);
    printf("─────────────────────────────────────────────────────────────\n");

    sqlite3_close(db);
    return EXIT_SUCCESS;
}