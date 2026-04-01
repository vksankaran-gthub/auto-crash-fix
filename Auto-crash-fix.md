## Generation of PR with a fix for crash with the mini-dump from the stack trace portal
## The User will input a Finger print that is present in the stack trace portal
## The automation tool will fetch the version of the build in which the crash is observed along with the minidump info which would contain the name of the library or the executable binary or the script that has crashed
## The automation tool shall fetch the recipe that packages this library / executable / script file and shall locate the respective repository. Using the yocto bitbake utilities the recipe contributing to the respective library / bin /script shall be identified, which will lead to the code repository that is fetched by the recipe. 
## The automation tool also gets the backtrace of the function that has crashed from the stack trace portal
## The tool feeds these information to the Co-Pilot AI and gets an appropriate fix
## A build is triggered with the code changes provided by the Co-Pilot. IF the build is successful, download it into a box and run the specific test cases for that component
## If the tests pass and if there are no new crashes, raise a PR.