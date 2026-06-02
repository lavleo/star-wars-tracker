CC      = gcc
CFLAGS  = -Wall -Wextra -O2 -std=c11
LDFLAGS = -lcurl -lgumbo -lsqlite3 -lcjson

TARGET  = sw_crawler

.PHONY: all clean cleandb purge run crawl status

all: $(TARGET)

$(TARGET): source.c
	$(CC) $(CFLAGS) -o $@ source.c $(LDFLAGS)

crawl: $(TARGET)
	./$(TARGET)

run: crawl
	python3 dashboard.py

# Show completion stats without starting the server
status:
	@sqlite3 starwars_timeline.db \
	  "SELECT \
	     COUNT(*) || ' total entries' AS info \
	   FROM timeline WHERE active=1 \
	   UNION ALL \
	   SELECT \
	     COUNT(*) || ' completed' \
	   FROM timeline WHERE active=1 AND progress='Complete' \
	   UNION ALL \
	   SELECT \
	     COUNT(*) || ' remaining' \
	   FROM timeline WHERE active=1 AND progress!='' OR progress IS NULL \
	   UNION ALL \
	   SELECT \
	     ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM timeline WHERE active=1), 1) || '%  complete' \
	   FROM timeline WHERE active=1 AND progress='Complete';" \
	2>/dev/null || echo "[!] Database not found — run 'make run' first."

# Removes compiled binary only — database is untouched
clean:
	rm -f $(TARGET)

# Removes the database only
cleandb:
	rm -f starwars_timeline.db

# Removes everything (binary + database)
purge: clean cleandb