import pyiridium9602

if __name__ == "__main__":
    import sys

    port = "COM2"

    if len(sys.argv) > 1:
        port = sys.argv[1]
    pyiridium9602.run_server(port)
