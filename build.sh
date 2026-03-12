#!/bin/bash
# Build script for Render
set -e

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Build complete!"
