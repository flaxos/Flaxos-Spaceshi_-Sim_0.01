# convert_yaml_to_json.py
import yaml
import json
import os
import shutil
import sys

def convert_yaml_to_json(input_dir, output_dir):
    """
    Convert YAML files to JSON
    
    Args:
        input_dir (str): Directory containing YAML files
        output_dir (str): Directory to write JSON files to
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    count = 0
    
    # Check if input directory exists
    if not os.path.exists(input_dir):
        print(f"Input directory '{input_dir}' does not exist!")
        return 0
    
    for filename in os.listdir(input_dir):
        # Check if file is YAML
        if filename.endswith(('.yaml', '.yml')):
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, filename.rsplit('.', 1)[0] + '.json')
            
            print(f"Converting {input_path} to {output_path}")
            
            try:
                # Load YAML
                with open(input_path, 'r') as f:
                    data = yaml.safe_load(f)
                
                # Write JSON
                with open(output_path, 'w') as f:
                    json.dump(data, f, indent=2)
                    
                count += 1
            except Exception as e:
                print(f"Error converting {input_path}: {e}")
        # Copy JSON files directly
        elif filename.endswith('.json'):
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, filename)
            
            print(f"Copying {input_path} to {output_path}")
            
            try:
                shutil.copy2(input_path, output_path)
                count += 1
            except Exception as e:
                print(f"Error copying {input_path}: {e}")
    
    return count

if __name__ == "__main__":
    # Get input and output directories from command line arguments
    input_dir = "fleet"
    output_dir = "fleet_json"
    
    if len(sys.argv) > 1:
        input_dir = sys.argv[1]
    if len(sys.argv) > 2:
        output_dir = sys.argv[2]
        
    count = convert_yaml_to_json(input_dir, output_dir)
    print(f"Converted {count} files to {output_dir}")
    print(f"Next step: python -m hybrid.converter {output_dir} hybrid_fleet")
