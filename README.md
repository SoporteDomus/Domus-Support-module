Domus Support Module (v1.0.0)

This module streamlines the customer support workflow by integrating Zendesk historical data with an AI Agent to automate initial ticket responses.
 Overview
The primary goal of this version is to leverage historical context to improve AI-generated replies. The system follows a three-step process:

Extraction: Receives the "cause" or category of an incoming support ticket.

Context Retrieval: Queries the Zendesk API to retrieve the 10 most recent tickets associated with that specific cause.

AI Augmentation: Feeds both the new ticket and the historical context to an AI agent to generate a precise, data-driven primary response.

Objective
To provide AI agents with relevant background information, ensuring that preliminary responses are consistent with past resolutions and company standards.
