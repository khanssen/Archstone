\# from repo root

git add -A

git commit -m "alabama test"

git push



git add -A → stage everything (new/modified/deleted) repo-wide



git add . → stage new + modified under the current folder (no deletions)



git add -u → stage modified + deleted (no new files) repo-wide



git add -p → stage changes interactively (by hunk)



**Commit locally first, test and lint your code:**



git add .

git commit -m "local tested change"



**Push only when ready:**



git pull --rebase origin main   # make sure you’re up to date

git push origin main









**Script execution bypass**



Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

npm ci



