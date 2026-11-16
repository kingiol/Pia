"""PyInstaller entry point for the Pia Python runtime sidecar."""

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    from pia_runtime.cli import main
    main()
