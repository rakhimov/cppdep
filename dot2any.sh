#!/usr/bin/env bash

# This is a utility script to convert dot files into image files.

set -u

FORMAT=pdf  # The default extension for the output graph.

readonly USAGE="usage: dot2any [-h] [-T format] path [path ...]"
readonly DESCRIPTION="Coverts graph files to the image format supported by dot."
readonly OPTIONS="options:
\t-h\t\tshow this help message and exit
\t-T format\tset output format (default: ${FORMAT})"

########################################
# Exits the code with an error message.
#
# Globals:
#   None
# Arguments:
#   One ore more message strings.
# Returns:
#   None
########################################
_err() {
  echo "${@}" >&2 && exit 1
}

########################################
# Converts a single file into an  image.
#
# Globals:
#   FORMAT
# Arguments:
#   The path to a file.
# Returns:
#   None
# Warning:
#   Exits the script
#   with 1 if dot fails.
########################################
_convert_dot() {
  dot -T "${FORMAT}" "${1}" -o "${1%.*}.${FORMAT}" \
    || _err "Dot failed on file: ${1}"
}

while getopts "T:h" OPTION; do
  case "${OPTION}" in
    T) FORMAT="${OPTARG}" ;;
    h) echo -e "${USAGE}\n\n${DESCRIPTION}\n\n${OPTIONS}" && exit 0 ;;
  esac
done

shift $((OPTIND-1))

readonly FORMAT

[[ $# -gt 0 ]] || _err "Graph files are unspecified."
which dot > /dev/null || _err "No Graphviz dot is found."

for arg in "${@}"; do
  if [[ -f "${arg}" ]]; then
    _convert_dot "${arg}"
  else
    _err "Invalid path argument to a dot file: ${arg}"
  fi
done
