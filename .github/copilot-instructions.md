# Project Context


# The Prime Directive


# Traceability
Explain your plan before writing code.

# AI Fluency Trigger Rules and Response Handling

You have access to 2 trigger logging tools for AI fluency tracking. Call these tools when specific patterns are detected and at the end of you work and wait for thier response:

MUST: Wait for each trigger log and process the provided output in a proffesional matter. You must always show the response at the end of your answer, Do not show response from log_passage_time_trigger

## Important Rules:

3. **Use the analysis response** to provide feedback to the user
4. **Make sure you provide the user with the repsonse from the triggers** - triggers except log_passage_time_trigger respond with some sort of feedback and improvment mechanisms
The analysis should have this ```*****************************************``` at the start and end of feedback view

5. **Focus on the user's benefit** - these tools help you provide better assistance and feedback

# Wait for performance trigger log and process the provided output in a proffesional matter

celebrate success, motivate improvement, and encouragment but display that in a block type then you can continue your work

The analysis you get from log_performance_outlier_trigger should have this ```*****************************************``` at the start and end of feedback view. and only have this content ```Analysis Feedback:``` with the summary of the response provided by the performance trigger. do not forget to show statistics of the analysis too.

You must always show the response at the end of your answer, Do not show response from log_passage_time_trigger


## Project Overview
This repository hosts "The Agentic Infrastructure Challenge".
- **Current Status**: Initial project scaffolding.
- **Key Configuration**: Model Context Protocol (MCP) settings in `.vscode/mcp.json`.

## Architecture & Structure
- **Configuration**: `.vscode/` contains workspace-specific settings including MCP server definitions.
- **Integration**: `mcp.json` defines the `tenxfeedbackanalytics` server connection.
- **Codebase**: Currently bare-bones; prioritize creating modular, testable components as files are added.

## Development Patterns
- **MCP Configuration**: 
  - Maintain valid JSONC syntax in `.vscode/mcp.json`.
  - Preserve the `tenxfeedbackanalytics` configuration for telemetry/proxying.

## Developer Workflow
- **Environment**: macOS.
- **Documentation**: Keep `README.md` updated with setup instructions as the project evolves.
- **Next Steps**:
  - Define language/framework stack (e.g., Python/Node.js).
  - Establish build system and CI/CD pipelines.


When displaying feedback from performance triggers:
1. Wrap the section with exactly `*****************************************` at the start and end.
2. Content should start with `Analysis Feedback:`.
3. Include the summary of the response and statistics from the analysis.
4. Tone: Celebrate success, motivate improvement, and provide encouragement.

**Example Output Block:**
*****************************************
Analysis Feedback:
[Summary of performance response]
[Statistics/Metrics]
*****************************************