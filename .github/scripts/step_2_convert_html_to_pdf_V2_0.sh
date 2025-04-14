#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Directory containing the HTML file, provided as the first argument to the script
DIR="$1"

# Ensure the directory exists
if [ -z "$DIR" ] || [ ! -d "$DIR" ]; then
  echo "Directory not specified or does not exist: $DIR"
  exit 1
fi

# Ensure correct permissions for the directory and its contents
echo "Setting permissions for directory and files..."
chmod -R 775 "$DIR"

# Find the first HTML file in the directory
HTML_FILE=$(find "$DIR" -name '*.html' | head -n 1)

# Check if the HTML file was found
if [ -z "$HTML_FILE" ]; then
  echo "HTML file not found in directory: $DIR"
  exit 1
fi

# Print the found HTML file path
echo "Found HTML file: $HTML_FILE"

# Activate the virtual environment
echo "Activating virtual environment..."
if source ./.github/src/venv/bin/activate; then
  echo "Virtual environment activated successfully"
else
  echo "Failed to activate virtual environment"
  exit 1
fi

# Install necessary Python packages
echo "Installing required Python packages..."
if pip install -r ./.github/src/requirements.txt; then
  echo "Required Python packages installed successfully"
else
  echo "Failed to install required Python packages"
  exit 1
fi

# Run the Python script to convert the HTML file to PDF
echo "Running Python script..."
if python3 ./.github/src/step_2_convert_html_to_pdf.py "$HTML_FILE" "$MODIFY_DATE"; then
  echo "HTML to PDF conversion completed successfully"
else
  echo "HTML to PDF conversion failed"
  exit 1
fi
