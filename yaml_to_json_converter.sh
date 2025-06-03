#!/bin/bash
# Simple script to convert YAML files to JSON

# Create output directory
mkdir -p fleet_json

# Loop through all YAML files in fleet directory
for file in fleet/*.yaml; do
    # Get filename without extension
    filename=$(basename "$file" .yaml)
    
    # Create output path
    output_file="fleet_json/${filename}.json"
    
    echo "Converting $file to $output_file"
    
    # Copy content directly since the files are already in JSON format
    # just with .yaml extension
    cp "$file" "$output_file"
done
echo "Conversion complete. JSON files in fleet_json directory."
echo "Now run: python -m hybrid.converter fleet_json hybrid_fleet"
