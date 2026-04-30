# Nutrition-App

## Trello Link
https://trello.com/b/E9Ex153P/operational-plan
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
The goal for this project is to have a working application that enables it's users to track their foor intake. Along with just tracking their food it also keeps track of their calories, other nutritional information, a daily, weekly, and monthly report, and other QOL features. We have released the base application and are currently working on adding new features.  

## UI Design
The U/I design has been a focus on simplicity and usability. The goal was allow users to easily navigate the system and interact with features without any confusion. We are steadily enhancing the frontend to provide a better visual presentation and overall a better user experience.

## Coding Standards
Our code is in Python, so we are keeping to the Python coding standards.

## Documentation Standards
Our code is commented in order to help everybody understand what is being done in each section. 

## Development environment (stack)
For this project, our main programming language is Python (version 3.12). Within Python, we use the library Flask (in conjunction with HTML and CSS) for our web application for its ease of use and flexibility in deployment. We also use the PyTest library and the built-in UnitTest framework to conduct small-scale unit testing. Another testing framework we plan to use is Selenium, to automate the testing of the web application. A comprehensive list of libraries used in the project is available in 'requirements.txt'. We also use MySQLServer to hold our database. 
## Deployment Environment
Our product has so far been deployed only on our local machines, which are either Windows 10 or 11 running the latest versions of Python and all of our used libraries. We use MySQLServer 8.0.45 and have not modified the installation from the base installer. We have plans in the future to deploy the app to the cloud using Microsoft Azure. 
## Version Management
Our main version contril is GitHub. We use a combination of GitHub Desktop, GitHub in Visual Studio Code, and the CLI version to ensure all code is up to date and everyone is working on the same version of the project. We also create branches to develop larger features to segment it from the app while we're developing and before it is ready for release. Our main branch is used for documentation updates and small code changes/bug fixes rather than large releases. 
## Change Management / Bug tracking
We also use GitHub for change management, as it automatically tracks what lines have been updated and edited and by whom. To track bugs, we communicate among the team and leave comments in the code, although we plan to start using GitHub's bug tracking features after the sprint 4 release. 
## Definition of
Ready (when all are checked): 
- Description clearly explains the goal
- Acceptance criteria are written
- Dependencies are identified
- UX/UI expectations are defined (if applicable)
- Story is estimated by the team
- Story fits within one sprint
- Required data is available

Done (when all are checked):
- Data/Image upload works
- Model prediction returns correct class
- Nutrition scaled using fixed_nutrition.csv
- Results saved to database
- Results displayed to user
- Error handling implemented
- Tested with multiple foods
- Code pushed to repository

## DevOps
### The First Way
Under the first way, we started looking at our system as a whole instead of looking at the individual parts. We wanted to figure out what was impeding both our workflow and the flow of infomation inside the app, and looking at an overall view of the system helped us find those constraints. Upon finding our constraints, we worked to make them as efficient as they could be and maximize the value of our inputs and outputs. We also communicated, to never pass a defect to a downstream center - if a bug was found, we swarmed it and got it fixed immediately. 
### The Second Way
The second way is about making things visible and creating feedback loops. With our CI/CD pipelines, we generated constant feedback based on our pushes to GitHub. We wanted to shorten our time for testing and deployment and know what went wrong early. We also gave each other constant feedback throughought the project, pushing each member to be the best they could be.
### The Third Way
The third way was probably the easiest for us to implement, as it had been there for the start. Tyler's passion for machine learning and desire to learn more gave us our project idea, and most requirements derived from either customer needs or a group member's desire to learn. This pushed us to greater heights as we all wanted to see this project succeed and learn while doing it. We experimented, took risks, broke things, and learned at every step of the way. 

## Security Features
In our pursuit of enhanced security, we devoted some time to adding security features to our application. Primarily, this takes the form of password hashing. We use 30,000 rounds of SHA256, with the cipher iterating on itself. We also have basic cloud security functions - a certificate is necessary to access the database in Azure and we use Secrets in GitHub in the deployment pipeline to access Docker.
### **When setting up MySQL:
- Install and configure from https://www.oracle.com/mysql/technologies/mysql-enterprise-edition-downloads.html  (GO TO THE WINDOWS TAB)
  - really only need mysql-commercial folder
    - inside the mysql-commercial BIN folder, run mysql_configurator.exe
  - Configure root account with 'Barker123!' as password, for this project (or change in files)
- Install your python driver! Use 'pip install mysql-connector-python
- you can run createDB.py to create the NutriLog database in your system, but, it will be changed to check on startup if you already have the database
- then, you can probably run app.py to launch the web application
