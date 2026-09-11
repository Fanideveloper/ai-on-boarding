## Purpose

An MCP server that exposes the account-management surface as tools an assistant can call,
acting with the calling person's own privileges and disclosing to the assistant only the
fields each tool needs.

## ADDED Requirements

### Requirement: Act with the calling person's own privileges
Every tool SHALL act as the person who authenticated to the MCP server, obtaining that
person's own authentication token from the account system rather than a shared credential of
the server's own. A tool SHALL NOT be able to do anything the calling person could not do by
calling the account system directly.

#### Scenario: A non-administrator calls an administrative tool
- **WHEN** a person who is not an administrator calls a tool that requires administrative
  privileges
- **THEN** the tool is refused, and the refusal is the account system's own

#### Scenario: An administrator calls the same tool
- **WHEN** an administrator calls that tool
- **THEN** the tool succeeds

### Requirement: Expose a tool that lists accounts
The MCP server SHALL expose a tool that returns the account listing. Its name and description
SHALL describe what it returns without claiming any filter it does not apply.

#### Scenario: Listing accounts
- **WHEN** an administrator calls the listing tool with no country
- **THEN** the tool returns every account the account system lists

### Requirement: Expose a tool that lists accounts from a country
The MCP server SHALL expose a tool that returns only accounts recording a given country,
matched without regard to case.

#### Scenario: Listing accounts from a country
- **WHEN** an administrator calls the tool with a country
- **THEN** the tool returns only accounts recording that country

#### Scenario: Country named in a different case
- **WHEN** the tool is called with a country whose case differs from the recorded value
- **THEN** the same accounts are returned

### Requirement: Expose a tool that changes a password
The MCP server SHALL expose a tool that changes a password, able to change the caller's own
password given their current password, and able to change another account's password when the
caller is an administrator.

#### Scenario: Changing one's own password
- **WHEN** a caller invokes the tool for their own account with their current password and a
  valid new one
- **THEN** the password is changed and the tool reports that it was

#### Scenario: An administrator changing another account's password
- **WHEN** an administrator invokes the tool for another named account with a valid new
  password
- **THEN** that account's password is changed and the tool reports that it was

### Requirement: Disclose only the fields a tool needs
Each tool SHALL return only the fields that tool needs, discarding every other field the
account system returned before it reaches the assistant. Authentication tokens, passwords,
internal record identifiers, and email addresses SHALL never appear in a tool's result. The
restriction SHALL be applied where the account system's response is received, so that a tool
cannot widen it.

#### Scenario: Listing results
- **WHEN** any listing tool returns accounts
- **THEN** each entry carries only a username, a country, and a signup date

#### Scenario: A field the account system adds later
- **WHEN** the account system's response carries a field no tool asked for
- **THEN** that field does not appear in any tool's result

### Requirement: Report the account system's actual verdict
A tool SHALL report success only when the account system reported success. A refusal SHALL
NOT be presented as a success, and a tool SHALL NOT describe a password as changed unless the
account system confirmed the change.

#### Scenario: A refused password change
- **WHEN** the account system refuses a password change for any reason
- **THEN** the tool reports that the password was not changed, and does not report success

### Requirement: State a refusal in plain language
A refusal SHALL be reported in a sentence stating what was refused and why, not as a bare
status code. An assistant given an unexplained failure retries it or invents a result, so the
reason must be legible.

#### Scenario: An administrative tool refused to a non-administrator
- **WHEN** a caller without administrative privileges is refused the account listing
- **THEN** the refusal states that listing accounts requires administrative privileges

#### Scenario: A password refused for its length
- **WHEN** a password change is refused because the new password is too long
- **THEN** the refusal says the password was too long and states the maximum permitted length

### Requirement: Point a caller who lacks their current password at the reset flow
When a self-service password change is refused because the current password supplied was
wrong, the refusal SHALL direct the caller to the existing password reset flow rather than
offering any way to change the password without it.

#### Scenario: Wrong current password
- **WHEN** a self-service password change is refused for a wrong current password
- **THEN** the refusal says so and directs the caller to reset their password by email

### Requirement: Obtain a fresh authentication token once before failing
When the account system refuses a request because the authentication token the server holds is
no longer accepted, the server SHALL obtain a fresh token and retry the request once before
reporting a failure. A successful password change invalidates the caller's own tokens, so the
token a session holds can stop being accepted part-way through that session.

#### Scenario: A token that is no longer accepted
- **WHEN** the account system refuses a tool's request because the held authentication token
  is not accepted
- **THEN** the server obtains a fresh token, retries the request once, and reports the result
  of that retry

#### Scenario: A second refusal
- **WHEN** the retried request is refused for the same reason
- **THEN** the tool reports the failure rather than retrying again
