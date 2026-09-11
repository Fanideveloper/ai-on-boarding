## MODIFIED Requirements

### Requirement: Enforce a minimum password strength
The system SHALL reject a password shorter than 8 characters, longer than 128 characters, or
one that does not contain at least one letter and at least one digit. No other composition
rule applies. A password refused for its length SHALL be told which bound it crossed.

#### Scenario: Password too short
- **WHEN** signup is submitted with a password under 8 characters
- **THEN** the request is rejected and the response names the password field

#### Scenario: Password missing a letter or a digit
- **WHEN** signup is submitted with a password of 8 or more characters that lacks a letter, or
  lacks a digit
- **THEN** the request is rejected and the response names the password field

#### Scenario: Password too long
- **WHEN** signup is submitted with a password longer than 128 characters
- **THEN** the request is rejected, the response names the password field, and the message
  states the 128-character maximum

#### Scenario: Password at the maximum length
- **WHEN** signup is submitted with an otherwise valid password of exactly 128 characters
- **THEN** the account is created
