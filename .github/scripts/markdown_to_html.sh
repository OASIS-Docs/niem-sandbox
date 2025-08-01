#!/bin/bash
# Enterprise Markdown to HTML Converter Shell Script
# Optimized for performance, error handling, and maintainability

set -euo pipefail  # Exit on error, undefined vars, pipe failures
IFS=$'\n\t'       # Secure Internal Field Separator

# ============================================================================
# CONFIGURATION & CONSTANTS  
# ============================================================================

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
readonly VENV_PATH="${REPO_ROOT}/.github/src/venv"
readonly PYTHON_SCRIPT="${REPO_ROOT}/.github/src/step_1_markdown_to_html_converter_V3_0.py"
readonly LOGFILE="${REPO_ROOT}/conversion.log"

# Performance tracking
readonly START_TIME=$(date +%s.%N)

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

log() {
    local level="$1"
    shift
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} [${level}] $*" | tee -a "${LOGFILE}"
}

log_info() { log "INFO" "${BLUE}$*${NC}"; }
log_warn() { log "WARN" "${YELLOW}$*${NC}"; }
log_error() { log "ERROR" "${RED}$*${NC}"; }
log_success() { log "SUCCESS" "${GREEN}$*${NC}"; }

sanitize_path() {
    local path="$1"
    # Remove newlines, carriage returns, and trim whitespace
    path=$(echo "$path" | tr -d '\n\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    # Normalize path
    path=$(realpath -m "$path" 2>/dev/null || echo "$path")
    echo "$path"
}

validate_file_exists() {
    local file="$1"
    local description="$2"
    
    if [[ ! -f "$file" ]]; then
        log_error "$description not found: $file"
        return 1
    fi
    log_info "$description found: $file"
    return 0
}

validate_directory_exists() {
    local dir="$1"
    local description="$2"
    
    if [[ ! -d "$dir" ]]; then
        log_error "$description not found: $dir"
        return 1
    fi
    log_info "$description found: $dir"
    return 0
}

check_command() {
    local cmd="$1"
    if ! command -v "$cmd" &> /dev/null; then
        log_error "Required command not found: $cmd"
        return 1
    fi
    return 0
}

performance_report() {
    local end_time=$(date +%s.%N)
    local duration=$(echo "$end_time - $START_TIME" | bc -l 2>/dev/null || echo "N/A")
    log_success "Total execution time: ${duration}s"
}

cleanup() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        log_error "Script failed with exit code: $exit_code"
    fi
    performance_report
    exit $exit_code
}

# ============================================================================
# DEPENDENCY MANAGEMENT
# ============================================================================

check_system_dependencies() {
    log_info "Checking system dependencies..."
    
    local missing_deps=()
    local required_commands=("python3" "git" "bc" "realpath")
    
    for cmd in "${required_commands[@]}"; do
        if ! check_command "$cmd"; then
            missing_deps+=("$cmd")
        fi
    done
    
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        log_error "Missing system dependencies: ${missing_deps[*]}"
        log_error "Please install missing dependencies and try again"
        return 1
    fi
    
    log_success "All system dependencies available"
    return 0
}

setup_python_environment() {
    log_info "Setting up Python virtual environment..."
    
    # Create virtual environment if it doesn't exist
    if [[ ! -d "$VENV_PATH" ]]; then
        log_info "Creating virtual environment at: $VENV_PATH"
        python3 -m venv "$VENV_PATH" || {
            log_error "Failed to create virtual environment"
            return 1
        }
    else
        log_info "Virtual environment already exists: $VENV_PATH"
    fi
    
    # Activate virtual environment
    # shellcheck source=/dev/null
    source "$VENV_PATH/bin/activate" || {
        log_error "Failed to activate virtual environment"
        return 1
    }
    
    log_info "Virtual environment activated"
    
    # Upgrade pip
    log_info "Upgrading pip..."
    pip install --upgrade pip --quiet || {
        log_error "Failed to upgrade pip"
        return 1
    }
    
    # Install/upgrade dependencies
    log_info "Installing Python dependencies..."
    local dependencies=(
        "beautifulsoup4>=4.12.0"
        "requests>=2.31.0"
        "aiohttp>=3.8.0"
        "aiofiles>=23.0.0"
    )
    
    for dep in "${dependencies[@]}"; do
        log_info "Installing: $dep"
        pip install "$dep" --quiet || {
            log_error "Failed to install $dep"
            return 1
        }
    done
    
    log_success "Python environment setup completed"
    return 0
}

install_prettier() {
    log_info "Checking Prettier installation..."
    
    if check_command "prettier"; then
        log_info "Prettier already available"
        return 0
    fi
    
    if check_command "npm"; then
        log_info "Installing Prettier globally..."
        npm install -g prettier --silent || {
            log_error "Failed to install Prettier"
            return 1
        }
        log_success "Prettier installed successfully"
    else
        log_warn "npm not available, Prettier installation skipped"
        log_warn "Markdown formatting may not work"
    fi
    
    return 0
}

# ============================================================================
# MAIN PROCESSING FUNCTIONS
# ============================================================================

find_markdown_file() {
    local search_dir="$1"
    
    log_info "Searching for Markdown files in: $search_dir"
    
    # Find .md files (non-recursive for safety)
    local md_files
    mapfile -t md_files < <(find "$search_dir" -maxdepth 1 -type f -name "*.md" 2>/dev/null)
    
    if [[ ${#md_files[@]} -eq 0 ]]; then
        log_error "No Markdown files found in: $search_dir"
        return 1
    elif [[ ${#md_files[@]} -eq 1 ]]; then
        echo "${md_files[0]}"
        log_info "Found Markdown file: ${md_files[0]}"
        return 0
    else
        log_warn "Multiple Markdown files found:"
        printf '%s\n' "${md_files[@]}" | while read -r file; do
            log_warn "  - $file"
        done
        # Return the first one
        echo "${md_files[0]}"
        log_info "Using first file: ${md_files[0]}"
        return 0
    fi
}

set_directory_permissions() {
    local target_dir="$1"
    
    log_info "Setting appropriate permissions for: $target_dir"
    
    # Set directory permissions (owner: rwx, group: rwx, others: r-x)
    find "$target_dir" -type d -exec chmod 755 {} + 2>/dev/null || {
        log_warn "Could not set directory permissions (continuing anyway)"
    }
    
    # Set file permissions (owner: rw-, group: rw-, others: r--)
    find "$target_dir" -type f -exec chmod 644 {} + 2>/dev/null || {
        log_warn "Could not set file permissions (continuing anyway)"
    }
    
    log_info "Permissions updated"
}

run_conversion() {
    local md_file="$1"
    local git_repo_basedir="$2"
    local md_dir="$3"
    local format_flag="$4"
    local convert_flag="$5"
    
    log_info "Starting conversion process..."
    log_info "  Markdown file: $md_file"
    log_info "  Repository base: $git_repo_basedir"
    log_info "  Working directory: $md_dir"
    log_info "  Format markdown: $format_flag"
    log_info "  Convert to HTML: $convert_flag"
    
    # Validate Python script exists
    validate_file_exists "$PYTHON_SCRIPT" "Python conversion script" || return 1
    
    # Build command arguments
    local cmd_args=("$md_file" "$git_repo_basedir" "$md_dir")
    
    if [[ "$format_flag" == "true" ]]; then
        cmd_args+=("--md-format")
    fi
    
    if [[ "$convert_flag" == "true" ]]; then
        cmd_args+=("--md-to-html")
    fi
    
    # Add verbose logging in debug mode
    if [[ "${DEBUG:-false}" == "true" ]]; then
        cmd_args+=("--log-level" "DEBUG")
    fi
    
    # Execute Python script
    log_info "Executing Python conversion script..."
    python3 "$PYTHON_SCRIPT" "${cmd_args[@]}" || {
        log_error "Python conversion script failed"
        return 1
    }
    
    log_success "Conversion completed successfully"
    return 0
}

# ============================================================================
# MAIN EXECUTION FLOW
# ============================================================================

main() {
    local sync_path=""
    local format_markdown="false"
    local convert_to_html="false"
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --sync-path)
                sync_path="$2"
                shift 2
                ;;
            --md-format)
                format_markdown="true"
                shift
                ;;
            --md-to-html)
                convert_to_html="true"
                shift
                ;;
            --debug)
                export DEBUG="true"
                shift
                ;;
            --help|-h)
                show_usage
                exit 0
                ;;
            *)
                # Positional arguments for backward compatibility
                if [[ -z "$sync_path" ]]; then
                    sync_path="$1"
                elif [[ "$1" == "--md-format" ]]; then
                    format_markdown="true"
                elif [[ "$1" == "--md-to-html" ]]; then
                    convert_to_html="true"
                fi
                shift
                ;;
        esac
    done
    
    # Use environment variable if not provided via command line
    if [[ -z "$sync_path" && -n "${SYNC_PATH:-}" ]]; then
        sync_path="$SYNC_PATH"
    fi
    
    # Validate required parameters
    if [[ -z "$sync_path" ]]; then
        log_error "SYNC_PATH not provided. Use --sync-path argument or set SYNC_PATH environment variable"
        show_usage
        exit 1
    fi
    
    # Default behavior: both format and convert
    if [[ "$format_markdown" == "false" && "$convert_to_html" == "false" ]]; then
        format_markdown="true"
        convert_to_html="true"
    fi
    
    log_info "Starting Enterprise Markdown to HTML Converter"
    log_info "Repository root: $REPO_ROOT"
    log_info "Sync path: $sync_path"
    
    # Sanitize and validate paths
    local md_dir
    md_dir=$(sanitize_path "$sync_path")
    validate_directory_exists "$md_dir" "Target directory" || exit 1
    
    local git_repo_basedir
    git_repo_basedir=$(sanitize_path "$REPO_ROOT")
    validate_directory_exists "$git_repo_basedir" "Repository base directory" || exit 1
    
    # Set appropriate permissions
    set_directory_permissions "$md_dir"
    
    # Find markdown file
    local md_file
    md_file=$(find_markdown_file "$md_dir") || exit 1
    
    # Validate markdown file
    validate_file_exists "$md_file" "Markdown file" || exit 1
    
    # Check system dependencies
    check_system_dependencies || exit 1
    
    # Setup Python environment
    setup_python_environment || exit 1
    
    # Install Prettier if needed and available
    if [[ "$format_markdown" == "true" ]]; then
        install_prettier
    fi
    
    # Run the conversion
    run_conversion "$md_file" "$git_repo_basedir" "$md_dir" "$format_markdown" "$convert_to_html" || exit 1
    
    log_success "All operations completed successfully"
}

show_usage() {
    cat << EOF
Enterprise Markdown to HTML Converter

USAGE:
    $0 [OPTIONS]

OPTIONS:
    --sync-path PATH     Path to directory containing markdown file
    --md-format          Format markdown file using Prettier
    --md-to-html         Convert markdown to HTML
    --debug              Enable debug logging
    --help, -h           Show this help message

ENVIRONMENT VARIABLES:
    SYNC_PATH           Alternative way to specify sync path

EXAMPLES:
    # Convert and format (default behavior)
    $0 --sync-path "ndr/v6.0/psd01"
    
    # Only format markdown
    $0 --sync-path "ndr/v6.0/psd01" --md-format
    
    # Only convert to HTML
    $0 --sync-path "ndr/v6.0/psd01" --md-to-html
    
    # Use environment variable
    export SYNC_PATH="ndr/v6.0/psd01"
    $0 --md-format --md-to-html

EOF
}

# ============================================================================
# SCRIPT ENTRY POINT
# ============================================================================

# Set up signal handlers for cleanup
trap cleanup EXIT
trap 'log_error "Script interrupted by user"; exit 130' INT TERM

# Initialize logging
echo "# Enterprise Markdown Converter - $(date)" > "$LOGFILE"

# Execute main function
main "$@"