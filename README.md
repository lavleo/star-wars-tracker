# Running It Yourself

### Using GitHub (internal)
- The easiest method is to click 'Code' -> 'Open in a Codespace'
![image](https://github.com/user-attachments/assets/574c24db-71e5-4c72-9ed8-54d8929729b1)
- Then you can run it right from your WebPage

### Installing Gumbo and Running the Program in GitHub (internal)
To use Gumbo run the following commands in the terminal
```
sudo apt update
sudo apt install libgumbo-dev 
```
OR -> Open the command palette and search for
```
Codespaces: Rebuild Container
Select Full Rebuild
```    
✔ All dependencies will be installed via the Dockerfile

### Using Docker to Run the Project on a Linux host
If running directly on a linux host, build the docker container (provided) using the following command in the project directory:
```
docker build -t web-crawler:latest .devcontainer/
```

And run the development environment using the following docker command in the project directory:
```
docker run -it --rm -v "$PWD":/workspace web-crawler /bin/bash
root ➜ / $ cd workspace
root ➜ /workspace $ make
root ➜ /workspace $ ./crawler
```
    
## Features
Compiling:
```{bash}
make                        # To build

make run-single             # Runs with 1 thread
make run-threads THREADS=4  # Runs with 4 threads   # Potentially dangerous to other system processes?
make run-auto               # Runs with system threads

make clean                  # To refresh
```

### Timing 
This allows you to view the time taken by the webcrawler to finish, when modifying the number of Threads used you can see
- 1 thread time =  1.21 s +/- .3s
- 4 thread time = .81 s +/- .15s
