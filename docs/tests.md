# Test Plan
- We plan to expand our test suite as the time goes on, but our current tests include:

## Current
We currently have unit tests for:
  - password encryption and decryption
  - helper functions for the machine learning model (string normalization, integert to float conversion, scaling a nutrition entry based on grams)
  - flask routes
  - each function within flask pages (login, saving user details to the session)

## Planned
We plan to expand our test coverage to

## Other

We also currently have basic test automation. Our test_nutrilog file runs on each commit to the github, ensuring each function we already have works with any new content we add. Our database is tested as well, with our create_db script running and testing each commit. 

The machine learning model is tested extensively before the model's weights are exported and used in the main project.