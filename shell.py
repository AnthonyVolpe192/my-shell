import subprocess #Allows for subprocesses which can connect their input/output/error together and obtain return codes.
import os #Allows Python to interact with the operacting system and read/write to files.
import shlex # Allows for lexical analysis of shell-like syntaxes, making it easier to parse strings that resemble commands in Unix Shells. 


def tokenize(line):
    # Create a shlex "lexer" object, which knows how to split a shell-style
    # command string the way a real shell would by respecting quotes so that
    # "Program Files" stays together as one token instead of two.
    lexer = shlex.shlex(line, posix=True)

    # By default, shlex splits on its own definition of word boundaries,
    # which treats punctuation as separate tokens. whitespace_split=True
    # tells it to split ONLY on whitespace instead, so things like > or |
    # stay attached to whatever token they're part of.
    lexer.whitespace_split = True

    # By default, shlex treats backslash (\) as an escape character, like
    # Unix shells do. On Windows, backslash is the path separator
    # (C:\Users\Name), so this disables escaping to keep backslashes literal
    # instead of shlex trying to "escape" the next character.
    lexer.escape = ""

    # Convert the lexer (which yields tokens one at a time) into a plain
    # list of strings - e.g. 'cd "Program Files"' becomes
    # ['cd', 'Program Files'].
    return list(lexer)


def split_pipeline(tokens):
    # Break one big token list into separate "stages" wherever a bare |
    # token shows up. E.g. tokenizing 'dir | findstr txt' gives
    # ['dir', '|', 'findstr', 'txt'], and this turns that into
    # [['dir'], ['findstr', 'txt']] - one list of tokens per command.
    stages, current = [], []

    for tok in tokens:
        if tok == "|":
            # Hit a pipe symbol: the stage we were building is finished,
            # so save it and start collecting tokens for the next stage.
            stages.append(current)
            current = []
        else:
            # An ordinary token (command name, argument, filename, etc.)
            # belongs to whichever stage we're currently building.
            current.append(tok)

    # The last stage never gets terminated by a | token, so it has to be
    # appended manually after the loop ends. If there was no | at all,
    # this just means "one stage containing everything."        
    stages.append(current)
    return stages


def extract_redirection(tokens):
    # Walk through one stage's tokens and pull out any redirection
    # operators (>, >>, <) along with the filename that follows each one.
    # What's left over (args) is the actual command and its real arguments,
    # with the redirection syntax stripped out entirely.
    args, stdin_file, stdout_file, append = [], None, None, False
    i = 0

    while i < len(tokens):
        tok = tokens[i]

        if tok in (">", ">>", "<"):
            # A redirection operator always needs a filename right after
            # it. If there isn't one (e.g. the line just ends in ">"),
            # that's a user error we can't recover from silently.
            if i + 1 >= len(tokens):
                raise ValueError(f"expected a filename after {tok}")

            if tok == ">":
                # Overwrite mode: replace the file's contents entirely.
                stdout_file, append = tokens[i + 1], False
            elif tok == ">>":
                # Append mode: add to the end of the file instead of
                # replacing it.
                stdout_file, append = tokens[i + 1], True
            else:
                # tok == "<": read the command's input from this file
                # instead of the keyboard.
                stdin_file = tokens[i + 1]

            # Skip past both the operator and the filename we just
            # consumed, since neither belongs in the final argument list.    
            i += 2
        else:
            # A normal token - part of the command itself, not part of
            # any redirection.
            args.append(tok)
            i += 1

    return args, stdin_file, stdout_file, append


def run_pipeline(stage_token_lists):
    # Given a list of stages (each one a token list for a single command),
    # run all of them wired together: the first stage's output feeds the
    # second stage's input, and so on, exactly like a real shell pipeline.
 
    # First pass: figure out each stage's real command + any redirection
    # it wants, before actually launching anything.
    stages = []
    for stage_tokens in stage_token_lists:
        args, stdin_file, stdout_file, append = extract_redirection(stage_tokens)
        if not args:
            # Something like "dir | | findstr" would produce an empty
            # stage in the middle - not a valid pipeline.
            raise ValueError("empty command in pipeline")
        stages.append((args, stdin_file, stdout_file, append))

    # open_files tracks every file we open, so we can close them all at
    # the end. processes tracks every program we start, so we can wait
    # for all of them to finish. prev_stdout holds the previous stage's
    # output pipe, so the next stage can read from it.
    open_files, processes, prev_stdout = [], [], None

    for i, (args, stdin_file, stdout_file, append) in enumerate(stages):
        is_last = (i == len(stages) - 1)

        # Decide where this stage's input comes from.
        if stdin_file:
            # This stage has its own explicit "< file" redirection.
            stdin_src = open(stdin_file, "r")
            open_files.append(stdin_src)
        else:
            # Otherwise, feed it the previous stage's output pipe
            # (or None, if this is the very first stage).
            stdin_src = prev_stdout

        # Decide where this stage's output goes.
        if stdout_file:
            # This stage has its own explicit ">" or ">>" redirection.
            stdout_dst = open(stdout_file, "a" if append else "w")
            open_files.append(stdout_dst)
        elif not is_last:
            # Not the last stage in the pipeline, and no file redirection -
            # so its output needs to become a pipe the next stage can read.
            stdout_dst = subprocess.PIPE
        else:
            # The last stage with no redirection just prints normally to
            # the terminal, same as any other command.
            stdout_dst = None

        # Launch the actual program. Popen (unlike run) doesn't block, so
        # every stage can be started and running at the same time.
        proc = subprocess.Popen(subprocess.list2cmdline(args), shell=True,
                                 stdin=stdin_src, stdout=stdout_dst)
        processes.append(proc)

        # Once the next stage has been handed this pipe as its stdin, our
        # own reference to it must be closed. If we keep it open too, the
        # downstream process may never see "end of input" and can hang
        # forever waiting for more data that will never arrive.
        if prev_stdout is not None:
            prev_stdout.close()

        # Remember this stage's output pipe (if it has one) so the next
        # loop iteration can wire it into the following stage's stdin.    
        prev_stdout = proc.stdout if stdout_dst == subprocess.PIPE else None

    # Wait for every process in the pipeline to actually finish running
    # before returning control to the main loop.
    for proc in processes:
        proc.wait()

    # Clean up every file we opened along the way.    
    for f in open_files:
        f.close()


def main():
    while True:
        try:
            # Show the prompt and wait for the user to type something.
            command = input("$ ")
        except EOFError:
            # Ctrl+Z (Windows) or Ctrl+D (Unix) signals "no more input" -
            # treat that the same as typing "exit".
            print()
            break
        except KeyboardInterrupt:
            # Ctrl+C while sitting at the prompt: cancel whatever was being
            # typed and just show a fresh prompt, instead of quitting.
            print()
            continue

        stripped = command.strip()
        if stripped == "":
            # Nothing typed (just hit Enter) - go straight back to the
            # prompt instead of trying to "run" an empty command.
            continue

        try:
            # Break the raw text into individual tokens (command name,
            # arguments, quoted strings, redirection symbols, etc.).
            tokens = tokenize(stripped)
        except ValueError as e:
            # An unclosed quote or similar typo - shlex reports this
            # instead of silently guessing what was meant.
            print(f"Error: {e}")
            continue
        if not tokens:
            continue

        # Split on any | symbols to see if this is a pipeline or a single
        # plain command.
        stages = split_pipeline(tokens)

        if len(stages) == 1:
            # Only one stage means this isn't a pipeline, so built-in
            # commands (cd, pwd, exit) are allowed here. Built-ins can't
            # participate in a real pipeline, since a pipe connects two
            # actual OS processes together, and a built-in never spawns
            # one of its own.
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
                        # "cd" with no argument: show current location,
                        # matching real shell behavior.
                        print(os.getcwd())
                    else:
                        # Changing directory happens directly inside this
                        # program (not a subprocess), so it actually
                        # sticks between commands.
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
            # If it's not exit/cd/pwd, fall through below and run it as
            # an external command (possibly with its own redirection).

        try:
            # Either a genuine pipeline (2+ stages), or a single external
            # command that wasn't a built-in - both are handled the same
            # way by run_pipeline.
            run_pipeline(stages)
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}")
        except Exception as e:
            # A safety net for anything unanticipated, so a weird edge
            # case prints a message instead of crashing the whole shell.
            print(f"Error: {e}")

if __name__ == "__main__":
    # Only run main() when this file is executed directly, not if it's
    # ever imported by another script.
    main()