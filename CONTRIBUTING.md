# Working together on MediAgent AI

Use GitHub Desktop for the first setup and everyday sharing. Each teammate signs in
with their own GitHub account. Do not share passwords or access tokens.

## The words you will see

- **Repository:** the project files and their recorded change history.
- **Clone:** download a working copy of a repository onto your laptop.
- **Commit:** save a named snapshot of selected changes on your laptop.
- **Push:** upload your commits to GitHub.
- **Pull:** bring commits from GitHub into your local copy.
- **Branch:** a separate line of work for a feature or fix.
- **Pull request:** a request for the team to review and merge a branch.

Saving a file does not upload it. Committing does not upload it either. Push shares
the commits with the team. Fetch checks for updates; pull applies them locally.

## First setup for the owner

1. Install GitHub Desktop from https://desktop.github.com/ and sign in.
2. Use **File > Add local repository** and select `C:\mediagent_medical_search`.
3. If Desktop says the folder is not a Git repository, use its **create a repository
   here** option. Confirm the final folder is exactly the existing project folder,
   not a new nested folder. The repository folder name and display name can differ.
4. Review the files in Changes. The `data`, `tmp`, `output`, `node_modules` and
   `hackathon_deck` build folders must not appear. The finished team documents are
   in `docs/` instead.
5. Make an initial commit if Desktop has not already created it, then choose
   **Publish repository**. Choose a repository name such as `mediagent-ai` and set
   its visibility deliberately. Start private unless the hackathon requires public
   source. The repository name can differ from the existing local folder name.
6. On GitHub, open the repository's **Settings > Collaborators**, add the teammates'
   GitHub accounts, and have them accept their invitations.

## First setup for a teammate

1. Accept the invitation using your own GitHub account.
2. In GitHub Desktop, use **File > Clone repository**, select this repository, and
   choose a folder on your own laptop.
3. Follow README.md to install Python packages and download the Ollama model.
4. Start the app. It creates a separate local database on your laptop.

The repository does not contain patient data, the Ollama model, installed Python
packages or a running server. Cloning the code does not install those automatically.

## The routine for each piece of work

1. Choose the repository in Desktop. Use **Fetch origin**, then **Pull origin** if
   updates are available. Start from the current shared version.
2. Create a branch with a descriptive name such as `improve-patient-search`.
3. Edit and run the app. Run `python -m unittest discover -v` for code changes.
4. Review Changes in Desktop. Select only the files that belong to the change.
5. Write a useful summary, such as `Fix completed patient search`, and commit.
6. Use **Publish branch** the first time, or **Push origin** afterward.
7. Open a pull request for a teammate to review. Merge it after agreement and checks.
8. Everyone pulls the merged changes into their local main branch before new work.

If Git reports a conflict, two changes overlap. Compare both versions and keep the
intended combined result, then test it. Do not resolve a conflict by deleting the
whole project, overwriting a teammate's work or force pushing without agreement.

## Sharing is intentional

GitHub Desktop detects edited files automatically but does not commit and push each
file save. That review step helps keep unfinished code and local files out of shared
history. Start with commit and push for each finished task. Automatic upload on
every edit is not configured in this project.

Never commit real patient data, database files, credentials, model downloads or
dependency folders. `.gitignore` helps prevent untracked files from being added;
it cannot remove a sensitive file that was already committed. Use fictional data
for demonstrations.
