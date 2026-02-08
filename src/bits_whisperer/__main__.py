"""Entry point for BITS Whisperer."""


def main() -> None:
    """Launch the BITS Whisperer application."""
    # Prepend isolated site-packages to sys.path BEFORE any provider imports.
    # This ensures on-demand-installed SDKs are discoverable in frozen builds.
    from bits_whisperer.core.sdk_installer import init_sdk_path

    init_sdk_path()

    from bits_whisperer.app import BitsWhispererApp

    app = BitsWhispererApp()
    app.MainLoop()


if __name__ == "__main__":
    main()
