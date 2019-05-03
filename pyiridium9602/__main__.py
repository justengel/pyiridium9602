from .pyiridium import run_serial_log_file, run_communicator
from .pyiridium_server import run_server


if __name__ == "__main__":
    import sys
    import argparse

    port = ""
    filename = None

    # Command Line arguments
    parser = argparse.ArgumentParser(description="Build or install a Python library.")

    parser.add_argument('-p', type=str,
                        help="COM port to use",
                        default=port)

    parser.add_argument('-f', '--filename', type=str,
                        help='Filename to run a log file.',
                        default=filename)

    parser.add_argument('-s', action="store_true",
                        help="Run the server instead.")

    args, remain = parser.parse_known_args(sys.argv[1:])
    # sys.argv = sys.argv[:1] + remain

    if args.s:
        run_server(args.p)

    elif args.filename is not None:
        run_serial_log_file(args.filename, args.p)

    else:
        run_communicator(args.p)
