# slash_role_manager_bot.py

import discord
from discord import app_commands # Import app_commands
from discord.ext import commands
from discord.utils import get
import os

# --- Configuration ---
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ FATAL ERROR: The DISCORD_BOT_TOKEN environment variable is not set.")
    print("   Please set this variable in your hosting environment (e.g., Railway Variables).")
    exit()

# Using commands.Bot still works fine for handling events and the basic structure
# but we will primarily use bot.tree for app commands.
intents = discord.Intents.default()
intents.members = True
intents.message_content = True # Keep for potential future prefix commands or message listeners

# help_command=None as slash commands have built-in help via Discord UI
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# --- Event: Bot Ready ---
@bot.event
async def on_ready():
    """Called when the bot is ready and has finished syncing commands."""
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('Syncing application commands...')
    try:
        # Sync commands globally. Can take up to an hour to propagate initially.
        # For testing on a single server, use:
        # synced = await bot.tree.sync(guild=discord.Object(id=YOUR_SERVER_ID))
        # Replace YOUR_SERVER_ID with your actual server ID (as an integer)
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} application command(s).')
    except Exception as e:
        print(f'Error syncing commands: {e}')
    print('Bot is ready!')
    print('------')
    await bot.change_presence(activity=discord.Game(name="/help for commands"))

# --- App Command Error Handling ---
# We need a specific listener for app command errors
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Handles errors specifically for application commands."""
    if isinstance(error, app_commands.CommandNotFound):
        await interaction.response.send_message("Sorry, I don't recognize that command.", ephemeral=True)
    elif isinstance(error, app_commands.MissingPermissions):
        missing_perms = ", ".join(f"`{perm}`" for perm in error.missing_permissions)
        await interaction.response.send_message(f"🚫 **Permission Denied:** You need the following permission(s) to use this command: {missing_perms}.", ephemeral=True)
    elif isinstance(error, app_commands.BotMissingPermissions):
        missing_perms = ", ".join(f"`{perm}`" for perm in error.missing_permissions)
        await interaction.response.send_message(f"🤖 **Bot Permission Error:** I don't have the required permission(s) to do that: {missing_perms}. Please grant me the necessary permissions.", ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure): # Catches failed permission checks or custom checks
        await interaction.response.send_message("🚫 You do not have permission to use this command.", ephemeral=True)
    elif isinstance(error, app_commands.CommandInvokeError):
         # Errors raised within the command's execution
        original = error.original
        if isinstance(original, discord.Forbidden):
             # Discord API permission errors (often hierarchy)
             await interaction.response.send_message(f"🚫 **Discord Permissions Error:** I lack the necessary permissions on Discord's side to perform this action. This often happens due to **role hierarchy** (my highest role must be above the role/member I'm trying to manage) or missing permissions.", ephemeral=True)
        else:
            print(f'Unhandled error in app command {interaction.command.name if interaction.command else "Unknown"}: {original}')
            # Send a generic error message, possibly deferring if not already done
            if not interaction.response.is_done():
                await interaction.response.send_message("⚙️ An unexpected error occurred while running the command.", ephemeral=True)
            else: # If we already deferred, use followup
                await interaction.followup.send("⚙️ An unexpected error occurred while running the command.", ephemeral=True)
    else:
        print(f'Unhandled app command error type: {type(error).__name__} - {error}')
        if not interaction.response.is_done():
            await interaction.response.send_message("🤔 An unknown error occurred.", ephemeral=True)
        else:
             await interaction.followup.send("🤔 An unknown error occurred.", ephemeral=True)

# Add the error handler to the tree
bot.tree.on_error = on_app_command_error


# --- Slash Command: Help ---
@bot.tree.command(name="help", description="Shows information about available commands.")
async def slash_help(interaction: discord.Interaction):
    """Provides help information via slash command."""
    embed = discord.Embed(
        title="🤖 GJ Team Role Manager Bot Help",
        description="Here are the available slash commands:",
        color=discord.Color.purple()
    )
    # Manually list commands as bot.commands won't easily list app commands for help embeds
    embed.add_field(
        name="🛠️ Role Management",
        value=("/createrole `role_name` - Creates a new role.\n"
               "/deleterole `role_name` - Deletes a role.\n"
               "/giverole `user` `role_name` - Assigns a role.\n"
               "/takerole `user` `role_name` - Removes a role."),
        inline=False
    )
    embed.add_field(
        name="ℹ️ Other",
        value="/help - Shows this message.",
        inline=False
    )
    embed.set_footer(text="You need 'Manage Roles' permission for most role commands.")
    # Use ephemeral=True to only show the message to the user who used the command
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- Slash Command: Create Role ---
# Use describe decorator for better help text in Discord UI
@bot.tree.command(name="createrole", description="Creates a new role in the server.")
@app_commands.describe(role_name="The exact name for the new role.")
@app_commands.checks.has_permissions(manage_roles=True) # User permission check
@app_commands.checks.bot_has_permissions(manage_roles=True) # Bot permission check
async def slash_createrole(interaction: discord.Interaction, role_name: str):
    """Slash command to create a new role."""
    guild = interaction.guild
    if not guild: # Should not happen in guild commands, but good practice
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return

    existing_role = get(guild.roles, name=role_name)
    if existing_role:
        await interaction.response.send_message(f"⚠️ A role named **{role_name}** already exists!", ephemeral=True)
        return

    if len(role_name) > 100:
        await interaction.response.send_message("❌ Role name cannot be longer than 100 characters.", ephemeral=True)
        return

    try:
        # Defer the response as role creation might take a moment
        await interaction.response.defer(ephemeral=True) # ephemeral=True makes deferral message hidden
        new_role = await guild.create_role(name=role_name, reason=f"Created by {interaction.user} via slash command.")
        # Use followup after deferring
        await interaction.followup.send(f"✅ Successfully created role: {new_role.mention}", ephemeral=False) # Make success message visible
    except discord.Forbidden:
        # This error should ideally be caught by the BotMissingPermissions handler,
        # but can be caught here as a fallback.
        if not interaction.response.is_done(): # Check if we already responded (e.g., in defer)
             await interaction.response.send_message("🚫 **Bot Permission Error:** I don't have permission to create roles.", ephemeral=True)
        else:
             await interaction.followup.send("🚫 **Bot Permission Error:** I don't have permission to create roles.", ephemeral=True)
    except Exception as e:
        print(f"Error in /createrole: {e}")
        if not interaction.response.is_done():
             await interaction.response.send_message(f"⚙️ An unexpected error occurred: {e}", ephemeral=True)
        else:
            await interaction.followup.send(f"⚙️ An unexpected error occurred: {e}", ephemeral=True)

# --- Slash Command: Delete Role ---
@bot.tree.command(name="deleterole", description="Deletes an existing role by its exact name.")
@app_commands.describe(role_name="The exact name of the role to delete.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_deleterole(interaction: discord.Interaction, role_name: str):
    """Slash command to delete a role."""
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return

    role_to_delete = get(guild.roles, name=role_name)
    if not role_to_delete:
        await interaction.response.send_message(f"❓ Could not find a role named **{role_name}**. Remember, names are case-sensitive.", ephemeral=True)
        return

    # Safety Checks (similar to before)
    if role_to_delete == guild.default_role:
        await interaction.response.send_message("🚫 Cannot delete the `@everyone` role.", ephemeral=True)
        return
    if role_to_delete >= guild.me.top_role and guild.me != guild.owner:
        await interaction.response.send_message(f"🚫 **Hierarchy Error:** I cannot delete {role_to_delete.mention} as it's higher than or equal to my role.", ephemeral=True)
        return
    if role_to_delete.is_integration() or role_to_delete.is_premium_subscriber() or role_to_delete.is_bot_managed():
         await interaction.response.send_message(f"⚠️ Cannot delete {role_to_delete.mention} as it's managed by Discord or an integration.", ephemeral=True)
         return

    try:
        await interaction.response.defer(ephemeral=True)
        role_name_saved = role_to_delete.name
        await role_to_delete.delete(reason=f"Deleted by {interaction.user} via slash command.")
        await interaction.followup.send(f"✅ Successfully deleted role: **{role_name_saved}**", ephemeral=False) # Visible confirmation
    except discord.Forbidden:
         if not interaction.response.is_done(): await interaction.response.send_message("🚫 **Bot Permission Error:** I lack permission to delete this role.", ephemeral=True)
         else: await interaction.followup.send("🚫 **Bot Permission Error:** I lack permission to delete this role.", ephemeral=True)
    except Exception as e:
        print(f"Error in /deleterole: {e}")
        if not interaction.response.is_done(): await interaction.response.send_message(f"⚙️ An unexpected error occurred: {e}", ephemeral=True)
        else: await interaction.followup.send(f"⚙️ An unexpected error occurred: {e}", ephemeral=True)

# --- Slash Command: Give Role ---
# Use discord.Member type hint for user input
@bot.tree.command(name="giverole", description="Assigns a role to a specified member.")
@app_commands.describe(user="The user to give the role to.", role_name="The exact name of the role to assign.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_giverole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    """Slash command to give a role to a member."""
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return

    role_to_give = get(guild.roles, name=role_name)
    if not role_to_give:
        await interaction.response.send_message(f"❓ Could not find a role named **{role_name}**. Check spelling and case.", ephemeral=True)
        return

    # Hierarchy Checks
    if role_to_give >= guild.me.top_role and guild.me != guild.owner:
        await interaction.response.send_message(f"🚫 **Hierarchy Error:** I cannot assign {role_to_give.mention} as it's higher than or equal to my role.", ephemeral=True)
        return
    # Prevent users from assigning roles higher than themselves
    if role_to_give >= interaction.user.top_role and interaction.user != guild.owner:
        await interaction.response.send_message(f"🚫 **Permission Denied:** You cannot assign {role_to_give.mention} as it's higher than or equal to your own highest role.", ephemeral=True)
        return
    if role_to_give in user.roles:
        await interaction.response.send_message(f"ℹ️ {user.mention} already has the role {role_to_give.mention}.", ephemeral=True)
        return

    try:
        await interaction.response.defer(ephemeral=True)
        await user.add_roles(role_to_give, reason=f"Role added by {interaction.user} via slash command.")
        await interaction.followup.send(f"✅ Successfully gave the role {role_to_give.mention} to {user.mention}.", ephemeral=False)
    except discord.Forbidden:
         if not interaction.response.is_done(): await interaction.response.send_message("🚫 **Bot Permission Error:** I lack permission to assign this role.", ephemeral=True)
         else: await interaction.followup.send("🚫 **Bot Permission Error:** I lack permission to assign this role.", ephemeral=True)
    except Exception as e:
        print(f"Error in /giverole: {e}")
        if not interaction.response.is_done(): await interaction.response.send_message(f"⚙️ An unexpected error occurred: {e}", ephemeral=True)
        else: await interaction.followup.send(f"⚙️ An unexpected error occurred: {e}", ephemeral=True)


# --- Slash Command: Take Role ---
@bot.tree.command(name="takerole", description="Removes a role from a specified member.")
@app_commands.describe(user="The user to remove the role from.", role_name="The exact name of the role to remove.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_takerole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    """Slash command to remove a role from a member."""
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return

    role_to_take = get(guild.roles, name=role_name)
    if not role_to_take:
        await interaction.response.send_message(f"❓ Could not find a role named **{role_name}**. Check spelling and case.", ephemeral=True)
        return

    # Hierarchy Checks
    if role_to_take >= guild.me.top_role and guild.me != guild.owner:
        await interaction.response.send_message(f"🚫 **Hierarchy Error:** I cannot remove {role_to_take.mention} as it's higher than or equal to my role.", ephemeral=True)
        return
    if role_to_take >= interaction.user.top_role and interaction.user != guild.owner:
        await interaction.response.send_message(f"🚫 **Permission Denied:** You cannot remove {role_to_take.mention} as it's higher than or equal to your own highest role.", ephemeral=True)
        return
    if role_to_take not in user.roles:
        await interaction.response.send_message(f"ℹ️ {user.mention} doesn't have the role {role_to_take.mention}.", ephemeral=True)
        return
    if role_to_take.is_integration() or role_to_take.is_premium_subscriber() or role_to_take.is_bot_managed():
         await interaction.response.send_message(f"⚠️ Cannot remove {role_to_take.mention} via this command as it's managed by Discord or an integration.", ephemeral=True)
         return

    try:
        await interaction.response.defer(ephemeral=True)
        await user.remove_roles(role_to_take, reason=f"Role removed by {interaction.user} via slash command.")
        await interaction.followup.send(f"✅ Successfully removed the role {role_to_take.mention} from {user.mention}.", ephemeral=False)
    except discord.Forbidden:
         if not interaction.response.is_done(): await interaction.response.send_message("🚫 **Bot Permission Error:** I lack permission to remove this role.", ephemeral=True)
         else: await interaction.followup.send("🚫 **Bot Permission Error:** I lack permission to remove this role.", ephemeral=True)
    except Exception as e:
        print(f"Error in /takerole: {e}")
        if not interaction.response.is_done(): await interaction.response.send_message(f"⚙️ An unexpected error occurred: {e}", ephemeral=True)
        else: await interaction.followup.send(f"⚙️ An unexpected error occurred: {e}", ephemeral=True)

# --- Placeholder for Your Highly Customized Assignment Logic (using App Commands) ---
# Example: Command to update TSB rank (you'd still need a verification process)
@bot.tree.command(name="verify_tsb_kills", description="(Admin) Verifies kills and updates TSB rank.")
@app_commands.describe(user="The user whose rank to update.", kills="The verified number of kills.")
@app_commands.checks.has_permissions(manage_roles=True) # Or a custom check/role check
async def slash_verify_tsb_kills(interaction: discord.Interaction, user: discord.Member, kills: int):
    await interaction.response.defer(ephemeral=True) # Defer as this might involve multiple steps

    guild = interaction.guild
    if not guild: # Should be checked by default but good practice
        await interaction.followup.send("Error: Cannot determine server.", ephemeral=True)
        return

    # --- Rank Logic (Same as before, but adapted for interaction) ---
    ranks = { # Role Name mapping
        50000: "TSB Apex", 40000: "TSB Legend", 30000: "TSB Grandmaster",
        20000: "TSB Strong", 10000: "TSB Elite", 5000: "TSB Adept", 0: "TSB Player"
    }
    target_role_name = None
    for threshold, name in sorted(ranks.items(), reverse=True):
        if kills >= threshold:
            target_role_name = name
            break

    if not target_role_name:
        await interaction.followup.send("Could not determine rank for the specified kills.", ephemeral=True)
        return

    target_role = get(guild.roles, name=target_role_name)
    if not target_role:
        await interaction.followup.send(f"Error: Target rank role '{target_role_name}' not found.", ephemeral=True)
        return

    # --- Remove Old Ranks ---
    tsb_rank_role_names = list(ranks.values())
    roles_to_remove = [role for role in user.roles if role.name in tsb_rank_role_names and role != target_role]
    removed_old = False
    if roles_to_remove:
        try:
            await user.remove_roles(*roles_to_remove, reason=f"Updating TSB Rank via /verify by {interaction.user}")
            removed_old = True
        except Exception as e:
            print(f"Error removing old rank roles for {user}: {e}")
            await interaction.followup.send(f"⚠️ Error removing old rank roles for {user.mention}, but attempting to add new one.", ephemeral=True)
            # Decide if you want to stop here or continue

    # --- Add New Rank ---
    if target_role not in user.roles:
        try:
            # Hierarchy check (Bot vs Target Role)
            if target_role >= guild.me.top_role and guild.me != guild.owner:
                 await interaction.followup.send(f"🚫 **Hierarchy Error:** I cannot assign the role {target_role.mention}.", ephemeral=True)
                 return

            await user.add_roles(target_role, reason=f"TSB Kills Verified ({kills}) by {interaction.user} via /verify")
            await interaction.followup.send(f"✅ Updated {user.mention}'s TSB rank to {target_role.mention} ({kills} kills).", ephemeral=False) # Success message visible
        except Exception as e:
            print(f"Error assigning new rank role for {user}: {e}")
            await interaction.followup.send(f"⚙️ Error assigning the new rank role {target_role.mention} to {user.mention}.", ephemeral=True)
    elif removed_old: # If old roles were removed but they already had the target role
         await interaction.followup.send(f"✅ Removed old rank roles for {user.mention}. They already have the correct rank {target_role.mention} for {kills} kills.", ephemeral=False)
    else: # If they already had the correct role and no old ones were removed
         await interaction.followup.send(f"ℹ️ {user.mention} already has the correct rank {target_role.mention} for {kills} kills.", ephemeral=True)


# --- Run the Bot ---
if __name__ == "__main__":
    print("Starting slash command bot...")
    try:
        bot.run(BOT_TOKEN)
    except discord.LoginFailure:
        print("❌ FATAL ERROR: Login failed. The DISCORD_BOT_TOKEN is invalid.")
    except discord.PrivilegedIntentsRequired:
        print("❌ FATAL ERROR: Privileged Intents (Server Members and/or Message Content) are required but not enabled.")
        print("   Go to your bot's application page on the Discord Developer Portal and enable them under the 'Bot' tab.")
    except Exception as e:
        print(f"❌ FATAL ERROR: An error occurred during bot startup: {e}")