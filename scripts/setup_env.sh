#!/bin/bash
# README Sync Manager Environment Setup Script
# This script should be sourced to set up the proper environment variables

# Load common environment variables
if [[ -f ~/.env_common ]]; then
    source ~/.env_common
else
    echo "Warning: ~/.env_common not found. Using fallback paths."
    export DATA_ROOT="$HOME/Developer/Code/Data"
    export SRV_DIR="$DATA_ROOT/srv"
    
    # Basic slugify function
    slugify() {
        local s="$1"
        s=$(echo "$s" | tr '[:upper:]' '[:lower:]')
        s=$(echo "$s" | sed -E 's/[^a-z0-9]+/_/g')
        s=$(echo "$s" | sed -E 's/^_+|_+$//g;s/_{2,}/_/g')
        echo "$s"
    }
    
    # Basic get_project_data function
    get_project_data() {
        local name="$(slugify "$1")"
        local dir="$SRV_DIR/$name"
        mkdir -p "$dir"
        echo "$dir"
    }
fi

# Set project-specific environment variables
slug=$(slugify "readme-flat")
export PROJECT_DATA_DIR=$(get_project_data "$slug")

echo "Environment setup complete:"
echo "  PROJECT_DATA_DIR: $PROJECT_DATA_DIR"
echo "  SRV_DIR: $SRV_DIR"
echo "  DATA_ROOT: $DATA_ROOT"