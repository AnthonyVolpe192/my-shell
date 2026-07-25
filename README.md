# Simple Command-Line Shell

A basic command-line shell written in Python, built as a learning project to
understand core operating system concepts like process execution, standard
I/O streams, and shell parsing.

## Features

- Runs any external Windows command (`dir`, `echo`, `whoami`, etc.)
- Built-in commands: `cd`, `pwd`, `exit`
- Handles quoted arguments with spaces (e.g. `cd "Program Files"`)
- Output/input redirection: `>`, `>>`, `<`
- Piping between commands: `|`
- Graceful error handling — invalid commands, missing files, and
  Ctrl+C/Ctrl+Z don't crash the shell

## Requirements

- Python 3.8 or newer

## Usage

$ dir
$ cd "Program Files"
$ echo hello > out.txt
$ dir | findstr txt

Type `exit` or press Ctrl+Z to quit.


## Test project made for educational purposes