on adding folder items to theFolder after receiving theItems
    set scriptPath to (POSIX path of (path to home folder)) & "Scripts/organizer.py"

    repeat with theItem in theItems
        set itemPath to POSIX path of theItem

        try
            do shell script "/usr/bin/env python3 " & quoted form of scriptPath & " " & quoted form of itemPath
        on error errMsg
            -- Errors are logged to ~/Downloads/.organizer_log.txt
            -- If the script never runs, see the Permissions section of README.md
            do shell script "echo '[Folder Action error] " & errMsg & "' >> ~/Downloads/.organizer_log.txt"
        end try
    end repeat
end adding folder items to
