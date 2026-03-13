#!/bin/bash
cd /home/kavia/workspace/code-generation/document-comparison-and-gap-analysis-platform-2208-2222/pmd_backend_service
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

