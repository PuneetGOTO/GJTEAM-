# slash_role_manager_bot.py (Version with Auto-Assign Separator Roles)

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
    exit() # Stop the script if token is missing

COMMAND_PREFIX = "!" # Legacy prefix (optional, as we focus on slash commands)

# --- Intents Configuration (Required) ---
intents = discord.Intents.default()
intents.members = True  # REQUIRED for on_member_join and member information
intents.message_content = True # Required for potential prefix commands or message listeners

# --- Bot Initialization ---
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

# --- Event: Bot Ready ---
@bot.event
async def on_ready():
    """Called when the bot is ready and has finished syncing commands."""
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('Syncing application commands...')
    try:
        # Sync commands globally. Can take up to an hour to propagate initially.
        # For faster testing, sync to a specific guild:
        # guild_id = YOUR_SERVER_ID_HERE # Replace with your server ID (integer)
        # synced = await bot.tree.sync(guild=discord.Object(id=guild_id))
        # print(f'Synced {len(synced)} application command(s) to guild {guild_id}.')
        synced = await bot.tree.sync() # Global sync
        print(f'Synced {len(synced)} application command(s) globally.')
    except Exception as e:
        print(f'Error syncing commands: {e}')
    print('Bot is ready!')
    print('------')
    await bot.change_presence(activity=discord.Game(name="/help for commands"))

# --- Event: Command Error Handling ---
@bot.event
async def on_command_error(ctx, error):
     # Basic error handling for potential legacy prefix commands
    if isinstance(error, commands.CommandNotFound):
        return # Ignore unknown prefix commands silently
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send(f"🚫 You lack permissions for this prefix command: {error.missing_permissions}")
    else:
        print(f"Error with prefix command {ctx.command}: {error}")

# --- Event: App Command Error Handling ---
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Handles errors specifically for application commands."""
    # (Error handling code from the previous slash command example goes here)
    # ... (Include the comprehensive error handling for app commands) ...
    if isinstance(error, app_commands.CommandNotFound):
        # This usually shouldn't happen with synced commands, but as a fallback
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
        original = error.original
        if isinstance(original, discord.Forbidden):
             await interaction.response.send_message(f"🚫 **Discord Permissions Error:** I lack the necessary permissions on Discord's side to perform this action (often due to role hierarchy).", ephemeral=True)
        else:
            print(f'Unhandled error in app command {interaction.command.name if interaction.command else "Unknown"}: {original}')
            message = "⚙️ An unexpected error occurred while running the command."
            if not interaction.response.is_done(): await interaction.response.send_message(message, ephemeral=True)
            else: await interaction.followup.send(message, ephemeral=True) # If we already deferred
    else:
        print(f'Unhandled app command error type: {type(error).__name__} - {error}')
        message = "🤔 An unknown error occurred."
        if not interaction.response.is_done(): await interaction.response.send_message(message, ephemeral=True)
        else: await interaction.followup.send(message, ephemeral=True)

# Add the error handler to the tree
bot.tree.on_error = on_app_command_error

# --- Event: Member Join - Assign Separator Roles & Welcome ---
@bot.event
async def on_member_join(member: discord.Member):
    """Automatically assigns specific separator roles and sends a welcome message."""
    guild = member.guild
    print(f'[+] {member.name} ({member.id}) joined {guild.name}') # Log member join

    # --- Define the EXACT names of your separator roles ---
    # !!! IMPORTANT: Replace these with the exact names you created !!!
    separator_role_names = [
        "————─────身份─────————",   # <-- 替换!
        "————─────通知─────————",   # <-- 替换!
        "————─────其他─────————"    # <-- 替换!
        # Add more separator role names here if needed
    ]

    roles_to_add = []
    roles_not_found_or_failed = [] # Track roles that weren't added

    # --- Assign Separator Roles ---
    for role_name in separator_role_names:
        role = get(guild.roles, name=role_name) # Find role by exact name
        if role:
            # Hierarchy Check (Bot needs role higher than separator role)
            if role < guild.me.top_role or guild.me == guild.owner:
                roles_to_add.append(role)
            else:
                reason = "权限/层级不足"
                print(f"⚠️ Warning: Cannot assign separator role '{role.name}' to {member.name}. Reason: Bot role too low.")
                roles_not_found_or_failed.append(f"{role_name} ({reason})")
        else:
            reason = "未找到"
            print(f"⚠️ Warning: Separator role '{role_name}' not found in server '{guild.name}'.")
            roles_not_found_or_failed.append(f"{role_name} ({reason})")

    if roles_to_add:
        try:
            await member.add_roles(*roles_to_add, reason="Auto-assigned separator roles on join")
            print(f"✅ Successfully assigned {len(roles_to_add)} separator roles to {member.name}.")
        except discord.Forbidden:
            print(f"❌ Error: Bot lacks 'Manage Roles' permission to assign roles to {member.name}.")
            roles_not_found_or_failed.extend([f"{r.name} (权限不足)" for r in roles_to_add]) # Mark all as failed due to permissions
        except discord.HTTPException as e:
            print(f"❌ Error: HTTP error while assigning roles to {member.name}: {e}")
            roles_not_found_or_failed.extend([f"{r.name} (HTTP错误)" for r in roles_to_add])
        except Exception as e:
             print(f"❌ Error: Unexpected error assigning roles to {member.name}: {e}")
             roles_not_found_or_failed.extend([f"{r.name} (未知错误)" for r in roles_to_add])

    # Report failures if any
    if roles_not_found_or_failed:
         print(f"Could not assign the following separator roles for {member.name}: {', '.join(roles_not_found_or_failed)}")

    # --- Optional: Send a Welcome Message ---
    # !!! IMPORTANT: Replace channel IDs below with your actual channel IDs !!!
    welcome_channel_id = 123456789012345678      # <--- 替换! 欢迎频道ID
    rules_channel_id = 123456789012345679        # <--- 替换! 规则频道ID
    roles_info_channel_id = 123456789012345680   # <--- 替换! 身份组介绍频道ID
    verification_channel_id = 123456789012345681 # <--- 替换! 实力认证频道ID

    welcome_channel = guild.get_channel(welcome_channel_id)
    if welcome_channel and isinstance(welcome_channel, discord.TextChannel): # Check if channel exists and is text channel
        try:
            embed = discord.Embed(
                title=f"🎉 欢迎来到 {guild.name}! 🎉",
                description=f"你好 {member.mention}! 很高兴你能加入 **GJ Team**！\n\n"
                            f"👇 **为了更好的体验, 请先:**\n"
                            f"- 阅读服务器规则: <#{rules_channel_id}>\n"
                            f"- 了解身份组信息: <#{roles_info_channel_id}>\n"
                            f"- 认证你的TSB实力: <#{verification_channel_id}>\n"
                            f"\n祝你在 GJ Team 玩得愉快!",
                color=discord.Color.from_rgb(100, 150, 255) # Example color: light blue
            )
            embed.set_thumbnail(url=member.display_avatar.url) # Show user's avatar
            embed.set_footer(text=f"你是服务器的第 {guild.member_count} 位成员！")
            await welcome_channel.send(embed=embed)
            print(f"Sent welcome message for {member.name}.")
        except discord.Forbidden:
            print(f"❌ Error: Bot lacks permission to send messages in welcome channel (ID: {welcome_channel_id}).")
        except Exception as e:
             print(f"❌ Error: Failed to send welcome message: {e}")
    elif welcome_channel_id != 123456789012345678: # Only warn if the ID was changed from the default placeholder
        print(f"⚠️ Warning: Welcome channel with ID {welcome_channel_id} not found or is not a text channel.")


# --- Slash Command: Help ---
# (Help command code from previous slash command example goes here)
# ... (Copy the slash_help function here) ...
@bot.tree.command(name="help", description="Shows information about available commands.")
async def slash_help(interaction: discord.Interaction):
    """Provides help information via slash command."""
    embed = discord.Embed(
        title="🤖 GJ Team Role Manager Bot Help",
        description="Here are the available slash commands:",
        color=discord.Color.purple()
    )
    embed.add_field(
        name="🛠️ Role Management",
        value=("/createrole `role_name` - Creates a new standard role.\n"
               "/deleterole `role_name` - Deletes a role.\n"
               "/giverole `user` `role_name` - Assigns a role.\n"
               "/takerole `user` `role_name` - Removes a role.\n"
               "/createseparator `label` - Creates a visual separator role."),
        inline=False
    )
    embed.add_field(
        name="ℹ️ Other",
        value="/help - Shows this message.",
        inline=False
    )
    embed.set_footer(text="<> = Required Argument. You need 'Manage Roles' permission for most role commands.")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- Slash Command: Create Role ---
# (Create role command code from previous slash command example goes here)
# ... (Copy the slash_createrole function here) ...
@bot.tree.command(name="createrole", description="Creates a new role in the server.")
@app_commands.describe(role_name="The exact name for the new role.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_createrole(interaction: discord.Interaction, role_name: str):
    """Slash command to create a new role."""
    guild = interaction.guild
    if not guild:
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
        await interaction.response.defer(ephemeral=True)
        new_role = await guild.create_role(name=role_name, reason=f"Created by {interaction.user} via slash command.")
        await interaction.followup.send(f"✅ Successfully created role: {new_role.mention}", ephemeral=False)
    except Exception as e: # Catch broader exceptions after defer
        print(f"Error in /createrole: {e}")
        # Check if Forbidden specifically if needed: if isinstance(e, discord.Forbidden): ...
        await interaction.followup.send(f"⚙️ An unexpected error occurred during role creation: {e}", ephemeral=True)


# --- Slash Command: Delete Role ---
# (Delete role command code from previous slash command example goes here)
# ... (Copy the slash_deleterole function here) ...
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
    # Safety Checks
    if role_to_delete == guild.default_role: await interaction.response.send_message("🚫 Cannot delete the `@everyone` role.", ephemeral=True); return
    if role_to_delete >= guild.me.top_role and guild.me != guild.owner: await interaction.response.send_message(f"🚫 **Hierarchy Error:** I cannot delete {role_to_delete.mention} as it's higher than or equal to my role.", ephemeral=True); return
    if role_to_delete.is_integration() or role_to_delete.is_premium_subscriber() or role_to_delete.is_bot_managed(): await interaction.response.send_message(f"⚠️ Cannot delete {role_to_delete.mention} as it's managed by Discord or an integration.", ephemeral=True); return
    try:
        await interaction.response.defer(ephemeral=True)
        role_name_saved = role_to_delete.name
        await role_to_delete.delete(reason=f"Deleted by {interaction.user} via slash command.")
        await interaction.followup.send(f"✅ Successfully deleted role: **{role_name_saved}**", ephemeral=False)
    except Exception as e:
        print(f"Error in /deleterole: {e}")
        await interaction.followup.send(f"⚙️ An unexpected error occurred during role deletion: {e}", ephemeral=True)


# --- Slash Command: Give Role ---
# (Give role command code from previous slash command example goes here)
# ... (Copy the slash_giverole function here) ...
@bot.tree.command(name="giverole", description="Assigns a role to a specified member.")
@app_commands.describe(user="The user to give the role to.", role_name="The exact name of the role to assign.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_giverole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    """Slash command to give a role to a member."""
    guild = interaction.guild
    if not guild: await interaction.response.send_message("...", ephemeral=True); return
    role_to_give = get(guild.roles, name=role_name)
    if not role_to_give: await interaction.response.send_message(f"❓ Role **{role_name}** not found.", ephemeral=True); return
    # Hierarchy Checks
    if role_to_give >= guild.me.top_role and guild.me != guild.owner: await interaction.response.send_message(f"🚫 Bot Hierarchy Error: Cannot assign {role_to_give.mention}.", ephemeral=True); return
    if role_to_give >= interaction.user.top_role and interaction.user != guild.owner: await interaction.response.send_message(f"🚫 User Hierarchy Error: Cannot assign {role_to_give.mention}.", ephemeral=True); return
    if role_to_give in user.roles: await interaction.response.send_message(f"ℹ️ {user.mention} already has {role_to_give.mention}.", ephemeral=True); return
    try:
        await interaction.response.defer(ephemeral=True)
        await user.add_roles(role_to_give, reason=f"Added by {interaction.user} via /giverole")
        await interaction.followup.send(f"✅ Gave {role_to_give.mention} to {user.mention}.", ephemeral=False)
    except Exception as e:
        print(f"Error in /giverole: {e}")
        await interaction.followup.send(f"⚙️ Error assigning role: {e}", ephemeral=True)


# --- Slash Command: Take Role ---
# (Take role command code from previous slash command example goes here)
# ... (Copy the slash_takerole function here) ...
@bot.tree.command(name="takerole", description="Removes a role from a specified member.")
@app_commands.describe(user="The user to remove the role from.", role_name="The exact name of the role to remove.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_takerole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    """Slash command to remove a role from a member."""
    guild = interaction.guild
    if not guild: await interaction.response.send_message("...", ephemeral=True); return
    role_to_take = get(guild.roles, name=role_name)
    if not role_to_take: await interaction.response.send_message(f"❓ Role **{role_name}** not found.", ephemeral=True); return
    # Hierarchy Checks
    if role_to_take >= guild.me.top_role and guild.me != guild.owner: await interaction.response.send_message(f"🚫 Bot Hierarchy Error: Cannot remove {role_to_take.mention}.", ephemeral=True); return
    if role_to_take >= interaction.user.top_role and interaction.user != guild.owner: await interaction.response.send_message(f"🚫 User Hierarchy Error: Cannot remove {role_to_take.mention}.", ephemeral=True); return
    if role_to_take not in user.roles: await interaction.response.send_message(f"ℹ️ {user.mention} doesn't have {role_to_take.mention}.", ephemeral=True); return
    if role_to_take.is_integration() or role_to_take.is_premium_subscriber() or role_to_take.is_bot_managed(): await interaction.response.send_message(f"⚠️ Cannot remove {role_to_take.mention} (managed role).", ephemeral=True); return
    try:
        await interaction.response.defer(ephemeral=True)
        await user.remove_roles(role_to_take, reason=f"Removed by {interaction.user} via /takerole")
        await interaction.followup.send(f"✅ Removed {role_to_take.mention} from {user.mention}.", ephemeral=False)
    except Exception as e:
        print(f"Error in /takerole: {e}")
        await interaction.followup.send(f"⚙️ Error removing role: {e}", ephemeral=True)


# --- Slash Command: Create Separator Role ---
# (Create separator command code from previous reply goes here)
# ... (Copy the slash_createseparator function here) ...
@bot.tree.command(name="createseparator", description="Creates a visual separator role.")
@app_commands.describe(label="The text to display inside the separator (e.g., '身分', '通知').")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_createseparator(interaction: discord.Interaction, label: str):
    """Slash command to create a visual separator role."""
    guild = interaction.guild
    if not guild: await interaction.response.send_message("...", ephemeral=True); return
    separator_name = f"▲─────{label}─────"
    if len(separator_name) > 100: await interaction.response.send_message(f"❌ Label too long.", ephemeral=True); return
    existing_role = get(guild.roles, name=separator_name)
    if existing_role: await interaction.response.send_message(f"⚠️ Separator **{separator_name}** already exists!", ephemeral=True); return
    try:
        await interaction.response.defer(ephemeral=True)
        new_role = await guild.create_role(
            name=separator_name, permissions=discord.Permissions.none(), color=discord.Color.light_grey(),
            hoist=False, mentionable=False, reason=f"Separator created by {interaction.user}")
        await interaction.followup.send(
            f"✅ Created separator: **{new_role.name}**\n**重要:** 请去 **服务器设置 -> 身份组** 手动拖动此身份组到目标位置！",
            ephemeral=False)
    except Exception as e:
        print(f"Error in /createseparator: {e}")
        await interaction.followup.send(f"⚙️ Error creating separator: {e}", ephemeral=True)


# --- Placeholder for Your Highly Customized Assignment Logic ---
# Example: /verify_tsb_kills command (from previous slash example)
# ... (You can copy the slash_verify_tsb_kills function here if needed) ...


# --- Run the Bot ---
if __name__ == "__main__":
    print("Starting bot...")
    try:
        # This runs the bot using the token loaded from the environment variable
        bot.run(BOT_TOKEN)
    except discord.LoginFailure:
        print("❌ FATAL ERROR: Login failed. The DISCORD_BOT_TOKEN is invalid.")
    except discord.PrivilegedIntentsRequired:
        print("❌ FATAL ERROR: Privileged Intents (Server Members and/or Message Content) are required but not enabled.")
        print("   Go to your bot's application page on the Discord Developer Portal and enable them under the 'Bot' tab.")
    except TypeError as e:
         if "unexpected keyword argument 'guild'" in str(e):
              print("❌ FATAL ERROR: Potential issue with discord.py version or async setup. Ensure libraries are up to date.")
         else:
              print(f"❌ FATAL ERROR: An unexpected TypeError occurred during bot startup: {e}")
    except Exception as e:
        # Catch any other exceptions during startup
        print(f"❌ FATAL ERROR: An error occurred during bot startup: {e}")