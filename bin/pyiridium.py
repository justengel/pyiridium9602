import pyiridium9602

if __name__ == "__main__":
    import sys
    import argparse

    port = "COM2"
    filename = None

    # Command Line arguments
    parser = argparse.ArgumentParser(description="Build or install a Python library.")

    parser.add_argument('-p', type=str,
                        help="COM port to use",
                        default=port)

    parser.add_argument('-f', '--filename', type=str,
                        help='Filename to run a log file.',
                        default=filename)

    pargs, remain = parser.parse_known_args(sys.argv[1:])
    # sys.argv = sys.argv[:1] + remain

    if pargs.filename is not None:
        pyiridium9602.run_serial_log_file(pargs.filename, pargs.p)
    else:
        pyiridium9602.run_communicator(pargs.p)
