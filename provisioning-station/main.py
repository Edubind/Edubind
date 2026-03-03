"""
main.py – Entry point for the Edubind Provisioning Station desktop application.

Usage:
    python main.py
"""

from station.ui.app import ProvisioningApp


def main() -> None:
    app = ProvisioningApp()
    app.mainloop()


if __name__ == "__main__":
    main()
