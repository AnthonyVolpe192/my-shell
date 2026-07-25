import subprocess
import os
import shlex

def tokenize(line):
    lexer = shlex.shlex(line, posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""
    return list(lexer)

def split_pipeline(tokens):
    stages, current = [], []
    for tok in tokens:
        if tok == "|":
            stages.append(current)
            current = []
        else:
            current.append(tok)
    stages.append(current)
    return stages

def extract_redirection(tokens):
    args, stdin_file, stdout_file, append = [], None, None, False
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in (">", ">>", "<"):
            if i + 1 >= len(tokens):
                raise ValueError(f"expected a filename after {tok}")
            if tok == ">":
                stdout_file, append = tokens[i + 1], False
            elif tok == ">>":
                stdout_file, append = tokens[i + 1], True
            else:
                stdin_file = tokens[i + 1]
            i += 2
        else:
            args.append(tok)
            i += 1
    return args, stdin_file, stdout_file, append

def run_pipeline(stage_token_lists):
    stages = []
    for stage_tokens in stage_token_lists:
        args, stdin_file, stdout_file, append = extract_redirection(stage_tokens)
        if not args:
            raise ValueError("empty command in pipeline")
        stages.append((args, stdin_file, stdout_file, append))

    open_files, processes, prev_stdout = [], [], None

    for i, (args, stdin_file, stdout_file, append) in enumerate(stages):
        is_last = (i == len(stages) - 1)

        if stdin_file:
            stdin_src = open(stdin_file, "r")
            open_files.append(stdin_src)
        else:
            stdin_src = prev_stdout

        if stdout_file:
            stdout_dst = open(stdout_file, "a" if append else "w")
            open_files.append(stdout_dst)
        elif not is_last:
            stdout_dst = subprocess.PIPE
        else:
            stdout_dst = None

        proc = subprocess.Popen(subprocess.list2cmdline(args), shell=True,
                                 stdin=stdin_src, stdout=stdout_dst)
        processes.append(proc)

        if prev_stdout is not None:
            prev_stdout.close()
        prev_stdout = proc.stdout if stdout_dst == subprocess.PIPE else None

    for proc in processes:
        proc.wait()
    for f in open_files:
        f.close()

def main():
    while True:
        try:
            command = input("$ ")
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()
            continue

        stripped = command.strip()
        if stripped == "":
            continue

        try:
            tokens = tokenize(stripped)
        except ValueError as e:
            print(f"Error: {e}")
            continue
        if not tokens:
            continue

        stages = split_pipeline(tokens)

        if len(stages) == 1:
            try:
                args, stdin_file, stdout_file, append = extract_redirection(stages[0])
            except ValueError as e:
                print(f"Error: {e}")
                continue
            if not args:
                continue
            cmd_name = args[0]

            if cmd_name == "exit":
                break
            elif cmd_name == "cd":
                try:
                    if len(args) < 2:
                        print(os.getcwd())
                    else:
                        os.chdir(args[1])
                except FileNotFoundError:
                    print(f"cd: no such file or directory: {args[1]}")
                except NotADirectoryError:
                    print(f"cd: not a directory: {args[1]}")
                except PermissionError:
                    print(f"cd: permission denied: {args[1]}")
                continue
            elif cmd_name == "pwd":
                print(os.getcwd())
                continue

        try:
            run_pipeline(stages)
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()