"""Setup script for bank reconciliation tool."""
from setuptools import setup, find_packages

setup(
    name="bank-recon-tool",
    version="1.0.0",
    description="Bank Reconciliation Tool for Sage Intacct",
    author="Your Name",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "requests>=2.31.0",
        "xmltodict>=0.13.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "python-dateutil>=2.8.2",
        "rapidfuzz>=3.5.0",
        "jellyfish>=1.0.0",
        "yfinance>=0.2.33",
        "fredapi>=0.5.1",
        "sqlalchemy>=2.0.0",
        "openpyxl>=3.1.0",
        "jinja2>=3.1.0",
        "click>=8.1.0",
        "rich>=13.0.0",
        "python-dotenv>=1.0.0",
        "pyyaml>=6.0.0",
    ],
    entry_points={
        "console_scripts": [
            "recon=src.cli:main",
        ],
    },
)
