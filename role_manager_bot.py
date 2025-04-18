# role_manager_bot.py

import discord
from discord.ext import commands
from discord.utils import get
import os # Import the os module to access environment variables

# --- Configuration ---
# Load the bot token from an environment variable for security.
# You will set this variable on your hosting platform (e.g., Railway).
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not BOT_TOKEN:
    # If the environment variable is not set, print an error and exit.
    # This prevents the bot from running without a token.
    print("❌ FATAL ERROR: The DISCORD_BOT_TOKEN environment variable is not set.")
    print("   Please set this variable in your hosting environment (e.g., Railway Variables).")
    exit() # Stop the script

COMMAND_PREFIX = "!" # You can change this command prefix

# --- Intents Configuration (Required for modern discord.py) ---
intents = discord.Intents.default()
intents.members = True  # Required to access member information (joining, roles)
intents.message_content = True # Required to read message content for commands

# --- Bot Initialization ---
# help_command=None disables the default help to use our custom one.
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

# --- Event: Bot Ready ---
@bot.event
async def on_ready():
    """Prints a message to the console when the bot has successfully connected."""
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print(f'Command Prefix: {COMMAND_PREFIX}')
    print('Bot is ready and listening for commands.')
    print('------')
    # Set a custom status activity (optional)
    await bot.change_presence(activity=discord.Game(name=f"Role Management | {COMMAND_PREFIX}help"))

# --- Event: Command Error Handling ---
@bot.event
async def on_command_error(ctx, error):
    """Handles common command errors and provides user-friendly feedback."""
    if isinstance(error, commands.CommandNotFound):
        # Optionally, inform the user the command doesn't exist, or just ignore.
        # await ctx.send(f"❓ Unknown command. Try `{COMMAND_PREFIX}help`.")
        return # Keep it silent for unknown commands
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ **Error:** Missing required argument: `{error.param.name}`.\nUse `{COMMAND_PREFIX}help {ctx.command.name}` for usage details.")
    elif isinstance(error, commands.MissingPermissions):
        missing_perms = ", ".join(f"`{perm}`" for perm in error.missing_permissions)
        await ctx.send(f"🚫 **Permission Denied:** You need the following permission(s) to use this command: {missing_perms}.")
    elif isinstance(error, commands.BotMissingPermissions):
        missing_perms = ", ".join(f"`{perm}`" for perm in error.missing_permissions)
        await ctx.send(f"🤖 **Bot Permission Error:** I don't have the required permission(s) to do that: {missing_perms}. Please grant me the necessary permissions in Server Settings -> Roles.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send(f"❓ **Error:** Could not find the member: `{error.argument}`. Please mention them correctly (`@User`) or use their exact User ID.")
    elif isinstance(error, commands.RoleNotFound):
         # Note: RoleNotFound might not be directly raised by default converters;
         # 'get' returning None is handled within commands. This is more for custom converters.
         await ctx.send(f"❓ **Error:** Could not find a role named: `{error.argument}`. Make sure the name is exact (case-sensitive).")
    elif isinstance(error, commands.CommandInvokeError):
        # Errors raised within the command's execution
        original = error.original
        if isinstance(original, discord.Forbidden):
             # This specifically catches 403 Forbidden errors from Discord API
             await ctx.send(f"🚫 **Discord Permissions Error:** I lack the necessary permissions on Discord's side to perform this action. This often happens due to **role hierarchy** (my highest role must be above the role/member I'm trying to manage) or missing permissions in the channel/server.")
        else:
            # For other errors within the command, log them and notify user
            print(f'Unhandled error in command {ctx.command}: {original}')
            await ctx.send("⚙️ An unexpected error occurred while running the command. The issue has been logged.")
    else:
        # Catch-all for other discord.py command errors
        print(f'Unhandled command error type: {type(error).__name__} - {error}')
        await ctx.send("🤔 An unknown error occurred while processing the command.")

# --- Custom Help Command ---
@bot.command(name='help', aliases=['h', 'commands'])
async def custom_help(ctx, *, command_name: str = None):
    """Shows help information for commands."""
    prefix = COMMAND_PREFIX # Get the bot's prefix for display

    if command_name:
        command = bot.get_command(command_name.lower()) # Allow case-insensitive lookup
        if command:
            # Show help for a specific command
            embed = discord.Embed(
                title=f"Command: {prefix}{command.name}",
                description=command.help or "No detailed description provided.",
                color=discord.Color.green() # Specific command help color
            )
            if command.aliases:
                embed.add_field(name="Aliases", value=", ".join(f"`{prefix}{alias}`" for alias in command.aliases), inline=False)
            # Construct usage string, handling potential lack of signature
            signature = command.signature or ""
            usage = f"`{prefix}{command.name} {signature}`"
            embed.add_field(name="Usage", value=usage, inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❓ Command `{command_name}` not found. Use `{prefix}help` to see all commands.")
    else:
        # Show general help embed listing all commands
        embed = discord.Embed(
            title="🤖 GJ Team Role Manager Bot Help",
            description=f"Hello! Here are the commands available. My prefix is `{prefix}`.",
            color=discord.Color.purple() # General help color
        )
        # Group commands for better readability
        role_mgmt_cmds = []
        other_cmds = []

        for command in bot.commands:
            if command.hidden: # Skip hidden commands if any
                continue
            if command.name in ['createrole', 'deleterole', 'giverole', 'takerole']:
                 # Add brief description or rely on the field value below
                 role_mgmt_cmds.append(f"`{prefix}{command.name}`")
            elif command.name == 'help':
                 other_cmds.append(f"`{prefix}{command.name}`")
            # Add other command categories if needed

        if role_mgmt_cmds:
             embed.add_field(
                 name="🛠️ Role Management",
                 value=(f"`{prefix}createrole <Role Name>` - Creates a new role.\n"
                        f"`{prefix}deleterole <Role Name>` - Deletes a role.\n"
                        f"`{prefix}giverole <@Member> <Role Name>` - Assigns a role.\n"
                        f"`{prefix}takerole <@Member> <Role Name>` - Removes a role."),
                 inline=False
             )

        if other_cmds:
            embed.add_field(
                name="ℹ️ Other",
                value=(f"`{prefix}help [Command Name]` - Shows this message or command details."),
                inline=False
            )

        embed.set_footer(text="<> = Required Argument, [] = Optional Argument. You need 'Manage Roles' permission for most commands.")
        await ctx.send(embed=embed)


# --- Command: Create Role ---
@bot.command(name='createrole')
@commands.has_permissions(manage_roles=True) # User needs Manage Roles perm
@commands.bot_has_permissions(manage_roles=True) # Bot needs Manage Roles perm
async def create_role(ctx, *, role_name: str):
    """Creates a new role with the specified name.
    Usage: !createrole <Role Name>
    Example: !createrole TSB Legend
    """
    guild = ctx.guild
    # Check if role already exists (case-sensitive check recommended by discord.py utils)
    existing_role = get(guild.roles, name=role_name)
    if existing_role:
        await ctx.send(f"⚠️ A role named **{role_name}** already exists in this server!")
        return

    # Limit role name length (Discord limit is 100)
    if len(role_name) > 100:
        await ctx.send("❌ Role name cannot be longer than 100 characters.")
        return

    try:
        # Create the role with default permissions and color
        new_role = await guild.create_role(name=role_name, reason=f"Created by {ctx.author} via bot command.")
        await ctx.send(f"✅ Successfully created role: {new_role.mention}")
    except discord.Forbidden:
        # This should be caught by @bot_has_permissions, but good to have as fallback
        await ctx.send("🚫 **Bot Permission Error:** I don't have permission to create roles.")
    except discord.HTTPException as e:
        await ctx.send(f"⚙️ An HTTP error occurred while creating the role: {e}")
    except Exception as e:
        await ctx.send(f"⚙️ An unexpected error occurred while creating the role: {e}")


# --- Command: Delete Role ---
@bot.command(name='deleterole')
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True)
async def delete_role(ctx, *, role_name: str):
    """Deletes an existing role by its exact name.
    Usage: !deleterole <Role Name>
    Example: !deleterole Old Role
    The bot's role must be higher than the role being deleted.
    """
    guild = ctx.guild
    # Find the role by name (case-sensitive)
    role_to_delete = get(guild.roles, name=role_name)

    if not role_to_delete:
        await ctx.send(f"❓ Could not find a role named **{role_name}**. Remember, names are case-sensitive.")
        return

    # Safety Checks
    if role_to_delete == guild.default_role: # @everyone role
        await ctx.send("🚫 Cannot delete the `@everyone` role.")
        return
    if role_to_delete >= ctx.guild.me.top_role and ctx.guild.me != guild.owner:
         # Check if bot is owner, owner bypasses hierarchy
        await ctx.send(f"🚫 **Hierarchy Error:** I cannot delete the role {role_to_delete.mention} because it is higher than or equal to my highest role. Please move my role higher in Server Settings -> Roles.")
        return
    if role_to_delete.is_integration() or role_to_delete.is_premium_subscriber() or role_to_delete.is_bot_managed():
         await ctx.send(f"⚠️ Cannot delete the role {role_to_delete.mention} because it is managed by Discord or an integration (e.g., Twitch, Bot specific role, Booster role).")
         return

    try:
        role_mention = role_to_delete.mention # Save mention in case needed after deletion
        role_name_saved = role_to_delete.name
        await role_to_delete.delete(reason=f"Deleted by {ctx.author} via bot command.")
        await ctx.send(f"✅ Successfully deleted role: **{role_name_saved}**")
    except discord.Forbidden:
        await ctx.send(f"🚫 **Bot Permission Error:** I don't have permission to delete the role {role_name}. This could also be a hierarchy issue.")
    except discord.HTTPException as e:
        await ctx.send(f"⚙️ An HTTP error occurred while deleting the role: {e}")
    except Exception as e:
        await ctx.send(f"⚙️ An unexpected error occurred while deleting the role: {e}")


# --- Command: Give Role ---
@bot.command(name='giverole')
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True)
async def give_role(ctx, member: discord.Member, *, role_name: str):
    """Assigns an existing role to a specified member.
    Usage: !giverole <@Member> <Role Name>
    Example: !giverole @Puneet TSB Legend
    The bot's role must be higher than the role being assigned.
    """
    guild = ctx.guild
    role_to_give = get(guild.roles, name=role_name) # Case-sensitive lookup

    if not role_to_give:
        await ctx.send(f"❓ Could not find a role named **{role_name}**. Check spelling and case.")
        return

    # Hierarchy Check: Bot vs Role to Give
    if role_to_give >= ctx.guild.me.top_role and ctx.guild.me != guild.owner:
        await ctx.send(f"🚫 **Hierarchy Error:** I cannot assign the role {role_to_give.mention} because it is higher than or equal to my highest role. Please move my role higher.")
        return
    # Hierarchy Check: Command User vs Role to Give (Prevent mods giving roles above them)
    if role_to_give >= ctx.author.top_role and ctx.author != guild.owner:
        await ctx.send(f"🚫 **Permission Denied:** You cannot assign the role {role_to_give.mention} because it is higher than or equal to your own highest role.")
        return
    # Check if member already has the role
    if role_to_give in member.roles:
        await ctx.send(f"ℹ️ {member.mention} already has the role {role_to_give.mention}.")
        return

    try:
        await member.add_roles(role_to_give, reason=f"Role added by {ctx.author} via bot command.")
        await ctx.send(f"✅ Successfully gave the role {role_to_give.mention} to {member.mention}.")
    except discord.Forbidden:
        await ctx.send(f"🚫 **Bot Permission Error:** I lack permission to assign the role {role_to_give.mention}. Check my permissions and role hierarchy.")
    except discord.HTTPException as e:
        await ctx.send(f"⚙️ An HTTP error occurred while giving the role: {e}")
    except Exception as e:
        await ctx.send(f"⚙️ An unexpected error occurred while giving the role: {e}")


# --- Command: Take Role ---
@bot.command(name='takerole')
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True)
async def take_role(ctx, member: discord.Member, *, role_name: str):
    """Removes a specific role from the specified member.
    Usage: !takerole <@Member> <Role Name>
    Example: !takerole @Puneet TSB Rookie
    The bot's role must be higher than the role being removed.
    """
    guild = ctx.guild
    role_to_take = get(guild.roles, name=role_name) # Case-sensitive lookup

    if not role_to_take:
        await ctx.send(f"❓ Could not find a role named **{role_name}**. Check spelling and case.")
        return

    # Hierarchy Check: Bot vs Role to Take
    if role_to_take >= ctx.guild.me.top_role and ctx.guild.me != guild.owner:
        await ctx.send(f"🚫 **Hierarchy Error:** I cannot remove the role {role_to_take.mention} because it is higher than or equal to my highest role.")
        return
    # Hierarchy Check: Command User vs Role to Take
    if role_to_take >= ctx.author.top_role and ctx.author != guild.owner:
        await ctx.send(f"🚫 **Permission Denied:** You cannot remove the role {role_to_take.mention} because it is higher than or equal to your own highest role.")
        return
    # Check if member actually has the role
    if role_to_take not in member.roles:
        await ctx.send(f"ℹ️ {member.mention} doesn't have the role {role_to_take.mention}.")
        return
    # Prevent removing integration/booster roles via this command
    if role_to_take.is_integration() or role_to_take.is_premium_subscriber() or role_to_take.is_bot_managed():
         await ctx.send(f"⚠️ Cannot remove the role {role_to_take.mention} via this command as it is managed by Discord or an integration.")
         return

    try:
        await member.remove_roles(role_to_take, reason=f"Role removed by {ctx.author} via bot command.")
        await ctx.send(f"✅ Successfully removed the role {role_to_take.mention} from {member.mention}.")
    except discord.Forbidden:
         await ctx.send(f"🚫 **Bot Permission Error:** I lack permission to remove the role {role_to_take.mention}. Check my permissions and role hierarchy.")
    except discord.HTTPException as e:
        await ctx.send(f"⚙️ An HTTP error occurred while removing the role: {e}")
    except Exception as e:
        await ctx.send(f"⚙️ An unexpected error occurred while removing the role: {e}")


# --- Placeholder for Your Highly Customized Assignment Logic ---
# You would add more @bot.command() or @bot.event listeners here
# based on your specific custom logic requirements. For example:
#
# @bot.listen('on_message')
# async def on_message_leveling(message):
#     # Basic leveling system logic (requires storing XP, usually in a database)
#     if message.author.bot: return # Ignore bots
#     # Add XP logic here...
#     # Check if user leveled up...
#     # If leveled up, find the appropriate role and assign it using add_roles
#     pass # Placeholder
#
# @bot.command(name='verifytsbkills')
# @commands.has_permissions(manage_roles=True) # Only allow specific users to verify
# async def verify_tsb_kills(ctx, member: discord.Member, kills: int):
#     """(Admin Only) Verifies kills and updates TSB rank role."""
#     # 1. Define kill thresholds and corresponding role names/IDs
#     ranks = {
#         50000: "TSB Apex", 40000: "TSB Legend", 30000: "TSB Grandmaster",
#         20000: "TSB Strong", 10000: "TSB Elite", 5000: "TSB Adept", 0: "TSB Player"
#     }
#     target_role_name = None
#     for threshold, name in sorted(ranks.items(), reverse=True):
#         if kills >= threshold:
#             target_role_name = name
#             break
#
#     if not target_role_name:
#         await ctx.send("Could not determine rank for the specified kills.")
#         return
#
#     target_role = get(ctx.guild.roles, name=target_role_name)
#     if not target_role:
#         await ctx.send(f"Error: Target rank role '{target_role_name}' not found in the server.")
#         return
#
#     # 2. Remove existing TSB rank roles (be careful with implementation)
#     tsb_rank_role_names = list(ranks.values()) # Get all possible rank names
#     roles_to_remove = [role for role in member.roles if role.name in tsb_rank_role_names and role != target_role]
#     if roles_to_remove:
#         try:
#             await member.remove_roles(*roles_to_remove, reason="Updating TSB Rank")
#         except Exception as e:
#             await ctx.send(f"Error removing old rank roles: {e}")
#             # Decide whether to proceed or stop
#
#     # 3. Add the new role if they don't have it
#     if target_role not in member.roles:
#         try:
#             # Ensure bot can assign this role (hierarchy)
#             if target_role >= ctx.guild.me.top_role and ctx.guild.me != ctx.guild.owner:
#                  await ctx.send(f"🚫 **Hierarchy Error:** I cannot assign the role {target_role.mention}.")
#                  return
#
#             await member.add_roles(target_role, reason=f"TSB Kills Verified ({kills}) by {ctx.author}")
#             await ctx.send(f"✅ Updated {member.mention}'s TSB rank to {target_role.mention} based on {kills} kills.")
#         except Exception as e:
#             await ctx.send(f"Error assigning new rank role: {e}")
#     else:
#         await ctx.send(f"{member.mention} already has the correct rank {target_role.mention} for {kills} kills.")


# --- Run the Bot ---
if __name__ == "__main__":
    print("Starting bot...")
    try:
        # This runs the bot with the token loaded from the environment variable
        bot.run(BOT_TOKEN)
    except discord.LoginFailure:
        print("❌ FATAL ERROR: Login failed. The provided Discord Bot Token is invalid.")
    except discord.PrivilegedIntentsRequired:
        print("❌ FATAL ERROR: Privileged Intents (Server Members and/or Message Content) are required but not enabled.")
        print("   Go to your bot's application page on the Discord Developer Portal and enable them under the 'Bot' tab.")
    except Exception as e:
        # Catch any other exceptions during startup
        print(f"❌ FATAL ERROR: An error occurred during bot startup: {e}")