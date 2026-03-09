# Nutrition-App

## Product Vision
  Nutrilog is for anybody looking to
be healthier.  This app will enable
them to improve their health in a
multitude of ways. The user will be
able to entire their food eaten and
their calories burnt from exercise.
This will help everybody improve
their lives. ​

## Project Goals + Release Plan 

## Coding Standards

## Documentation Standards

## Development environment (stack)
For this project, our main programming language is Python (version 3.12). Within Python, we use the library Flask (in conjunction with HTML and CSS) for our web application for its ease of use and flexibility in deployment. We also use the PyTest library and the built-in UnitTest framework to conduct small-scale unit testing. Another testing framework we plan to use is Selenium, to automate the testing of the web application. A comprehensive list of libraries used in the project is available in 'requirements.txt'. We also use MySQLServer to hold our database. 
## Deployment Environment
Our product has so far been deployed only on our local machines, which are either Windows 10 or 11 running the latest versions of Python and all of our used libraries. We use MySQLServer 8.0.45 and have not modified the installation from the base installer. We have plans in the future to deploy the app to the cloud using Microsoft Azure. 
## Version Management
Our main version contril is GitHub. We use a combination of GitHub Desktop, GitHub in Visual Studio Code, and the CLI version to ensure all code is up to date and everyone is working on the same version of the project. We also create branches to develop larger features to segment it from the app while we're developing and before it is ready for release. Our main branch is used for documentation updates and small code changes/bug fixes rather than large releases. 
## Change Management / Bug tracking
We also use GitHub for change management, as it automatically tracks what lines have been updated and edited and by whom. To track bugs, we communicate among the team and leave comments in the code, although we plan to start using GitHub's bug tracking features after the sprint 4 release. 
## Definition of 
  Ready:
  Done: 


**When setting up MySQL:
- Install and configure from https://www.oracle.com/mysql/technologies/mysql-enterprise-edition-downloads.html  (GO TO THE WINDOWS TAB)
  - really only need mysql-commercial folder
    - inside the mysql-commercial BIN folder, run mysql_configurator.exe
  - Configure root account with 'Barker123!' as password, for this project (or change in files)
- Install your python driver! Use 'pip install mysql-connector-python
- you can run createDB.py to create the NutriLog database in your system, but, it will be changed to check on startup if you already have the database
- then, you can probably run app.py to launch the web application
