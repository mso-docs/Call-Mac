# Using Call Mac

## Ask your first question

Choose **Back to conversation** beside **Appearance** to return to the conversation.
Describe what you are trying to do, what happened, and any error message you see.
You can ask about computers, phones, printers, software, networking, or programming.
Do not include passwords or other secrets.

Call Mac gives you one next step or asks a question. Follow the step and choose
**Fixed it**, **Still broken**, or **I don't understand**. You can add details in
**What happened?** before clicking. For questions, type your answer and choose
**Enter** (or the send arrow). Use **Shift+Enter** for a new line. General technology explanations have a follow-up box instead.

## Guest or saved profile?

Guest is the starting option. Choose your **Experience with tech** in the sidebar.
Guest conversations are temporary and are not saved to the local database.

To remember your devices and successful fixes, open **Saved profiles** in the
sidebar, enter your details, and click **Save profile**. This also selects that
profile. To switch to an existing profile, choose it under **Use Call Mac as**
and click **Apply user**. Saved profiles have separate histories and fixes.
Anyone using this app can select a profile; profiles do not have passwords.

## Start a different question

Click **New help task** above an active conversation. It pauses the current task
and lets you describe a new problem. Saved users' latest active tasks resume after
a restart. There is currently no browser for older tasks.

You can open **Help** and choose **Back to conversation** without clearing your conversation.
Submit any text you want to keep before switching pages; unsent form text may reset.

## Check the AI connection

Keep Ollama running. Open **AI connection** in the sidebar and click
**Test connection**. Use **Find installed Gemma models** to select another model.
A connection check confirms the server and model are available; generating an
answer can still take time. Model selection lasts for the current browser session.

For installation, server settings, smaller models, and common errors, select
**First-time setup** in the Help topic menu.

## Appearance and stopping the app

Use **Appearance** at the top right to choose System, Light, or Dark.
The sidebar starts hidden. Click the hamburger menu at the top left to open it.

To stop Call Mac, go to its terminal window and press **Ctrl+C**. Next time,
open Ollama and run the launch command in the first-time guide.

## Where your information goes

Saved profiles, conversations, and successful fixes live in `data/call_mac.db`
on the computer running Call Mac. Guest tasks live in the current browser session.
With local Ollama, AI requests stay on this computer. If you configured a remote
Ollama server, it receives your troubleshooting context.

AI advice can be incorrect. If an instruction is unclear, ask for clarification
before following it. Call Mac cannot inspect your device or confirm a fix itself.

If a response fails, **Try again** appears immediately. Your submitted message
and feedback are kept; retry asks the AI again without submitting them twice.

Click the **Call Mac** logo to return to the main page and start a fresh chat.
Your selected profile, experience, and saved fixes stay available.

If the server replies but its answer fails validation, open **Response validation
details**, retry, choose another Gemma model, or use **Revise your follow-up** to
add context. Revising keeps the conversation and replaces the latest submitted
reply; it does not start a new task.
