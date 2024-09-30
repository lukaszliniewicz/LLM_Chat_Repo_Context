# LLM Chat Repo Context

A simple GUI and command line tool to assist with providing chat LLMs with context about code repositories without the need to copy and paste multipe files manually. It outputs the directory structure of a repository as well as all/selected non-binary files, concatenated and saved as a text file. Processing a lot of code through an API, especially for big proprietary models like Claude Sonnet or Opus (which are the most capable), can get very expensive very fast. The chat interface is much cheaper if one does it a lot. An integration with Github is not always possible and the models can't execute any code or browse the internet (at least Claude can't), which is when this may come in handy. 

You can view a sample output from the [Pandrator](https://github.com/lukaszliniewicz/Pandrator) repository [here](https://github.com/lukaszliniewicz/LLM_Chat_Repo_Context/blob/main/example_pandrator.txt).

>[!Note]
>- This tool does not provide direct integration with LLMs
>- It's meant to support manual copying and pasting into chat interfaces
>- Token counts are estimates and may vary between different LLMs

## Features

- Analyze Git repositories
- Generate folder structure
- Concatenate file contents
- Count tokens in the output
- Select specific files to copy
- Save and load analysis sessions

## How to Use

1. Download the .exe file (created using PyInstaller)
2. Run the application
3. Enter a Git repository URL
4. Choose your analysis options
5. Click "Analyze Repository"
6. Use the output in your LLM chat conversations

## Use Cases and Examples

### 1. Code Review and Refactoring
Example: You're working on a large JavaScript project and want to refactor the authentication system.
- Use the tool to generate the folder structure, giving the LLM an overview of your project architecture.
- Select and copy the files related to authentication (e.g., `auth.js`, `login.js`, `userModel.js`).
- Ask the LLM: "Based on this structure and these files, how can I refactor the authentication system to be more secure and efficient?"

### 2. Implementing New Features
Example: You need to add a new API endpoint to your Flask application.
- Provide the full concatenated output of your Flask app to the LLM.
- Ask: "Given this existing Flask application, how would you implement a new endpoint for user profile updates?"

### 3. Debugging
Example: Your React application has a state management bug.
- Use the tool to copy your main React component files and any relevant state management code.
- Share these with the LLM and ask: "I'm experiencing issues with state updates in these components. Can you identify potential causes and suggest fixes?"

### 4. Code Style and Best Practices
Example: Ensuring consistent coding style across a Python project.
- Select a variety of Python files from different parts of your project.
- Ask the LLM: "Review these files and suggest changes to make the coding style more consistent. Also, point out any Python best practices we're not following."

### 5. Documentation Generation
Example: Creating documentation for a complex module.
- Use the tool to copy the contents of a specific module or set of related files.
- Ask the LLM: "Based on this code, can you generate comprehensive documentation including function descriptions, parameters, return values, and usage examples?"

### 6. Learning and Understanding Code
Example: You've joined a new project and need to understand the codebase quickly.
- Generate the folder structure of the entire project.
- Ask the LLM: "I want to understand how this project works. Which files would you like to read to be able to explain it to me in detail?"

### 7. Migrating Between Technologies
Example: Moving from jQuery to vanilla JavaScript.
- Copy your jQuery-heavy JavaScript files.
- Ask the LLM: "How would you rewrite these jQuery functions using modern vanilla JavaScript? Please provide examples for each conversion."

### 8. Security Auditing
Example: Checking for common security vulnerabilities in a Node.js application.
- Provide the package.json and main server files to the LLM.
- Ask: "Can you review these files for potential security vulnerabilities? Focus on areas like input validation, authentication, and dependency issues."

### 9. Performance Optimization
Example: Optimizing database queries in a Django application.
- Copy your Django models and views related to database operations.
- Ask the LLM: "Analyze these Django models and views. Can you suggest ways to optimize the database queries for better performance?"

### 10. API Design
Example: Designing a RESTful API for an existing application.
- Share the current codebase structure and any existing API-related files.
- Ask: "Based on this application structure, how would you design a comprehensive RESTful API? Include suggestions for endpoints, HTTP methods, and data formats."

## License

[MIT License](LICENSE)
