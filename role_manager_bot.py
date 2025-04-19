# slash_role_manager_bot.py (Version with All Features: Role Mgmt, Separators, Clear, Warn/Unwarn, Spam Detect, Auto Role)

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import get
import os
import datetime # Needed for spam detection timing

# --- Configuration ---
# Load the bot token from an environment variable for security.
# You will set this variable on your hosting platform (e.g., Railway).
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ FATAL ERROR: The DISCORD_BOT_TOKEN environment variable is not set.")
    print("   Please set this variable in your hosting environment (e.g., Railway Variables).")
    exit() # Stop the script if token is missing

COMMAND_PREFIX = "!" # Legacy prefix (mostly unused now)

# --- Intents Configuration (Required) ---
intents = discord.Intents.default()
intents.members = True      # REQUIRED for on_member_join, member info, member commands
intents.message_content = True # REQUIRED for on_message spam detection

# --- Bot Initialization ---
# help_command=None disables the default help to use our custom one.
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

# --- Spam Detection Configuration & Storage ---
SPAM_COUNT_THRESHOLD = 5  # Messages within window to trigger user spam
SPAM_TIME_WINDOW_SECONDS = 5 # Time window (seconds) for user spam
KICK_THRESHOLD = 3 # Warnings before kick (applies to both auto and manual warnings)

BOT_SPAM_COUNT_THRESHOLD = 8 # Messages within window to trigger bot spam alert
BOT_SPAM_TIME_WINDOW_SECONDS = 3 # Shorter time window for bots

# !!! 重要：替换成你的管理员/Mod身份组ID列表 !!!
MOD_ALERT_ROLE_IDS = [
    1362713317222912140, # <--- 替换!
    1362713953960198216  # <--- 替换!
    # 如果有更多，继续添加 , 111222333444555666
]

# In-memory storage (cleared on bot restart)
user_message_timestamps = {} # Stores {user_id: [timestamp1, timestamp2, ...]}
user_warnings = {} # Stores {user_id: warning_count}
bot_message_timestamps = {} # Stores {bot_user_id: [timestamp1, timestamp2, ...]}

# --- Event: Bot Ready ---
@bot.event
async def on_ready():
    """Called when the bot is ready and has finished syncing commands."""
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('Syncing application commands...')
    try:
        # --- Choose ONE sync method ---
        # 1. Global Sync (might take up to an hour initially)
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} application command(s) globally.')

        # 2. Guild Sync (for testing, nearly instant)
        # guild_id = 123456789012345678 # <<< REPLACE WITH YOUR SERVER ID (integer)
        # synced = await bot.tree.sync(guild=discord.Object(id=guild_id))
        # print(f'Synced {len(synced)} application command(s) to guild {guild_id}.')
        # --- End of sync method choice ---

    except Exception as e:
        print(f'Error syncing commands: {e}')
    print('Bot is ready!')
    print('------')
    await bot.change_presence(activity=discord.Game(name="/help for commands"))

# --- Event: Command Error Handling (Legacy Prefix Commands) ---
@bot.event
async def on_command_error(ctx, error):
    # Handles potential errors if legacy commands are somehow invoked
    if isinstance(error, commands.CommandNotFound): return # Ignore silently
    elif isinstance(error, commands.MissingPermissions): await ctx.send(f"🚫 PrefixCmd: Missing Perms: {error.missing_permissions}")
    else: print(f"Error with prefix command {ctx.command}: {error}")

# --- Event: App Command Error Handling ---
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Handles errors specifically for application commands."""
    # (Comprehensive error handling)
    if isinstance(error, app_commands.CommandNotFound): await interaction.response.send_message("Unknown command.", ephemeral=True)
    elif isinstance(error, app_commands.MissingPermissions): await interaction.response.send_message(f"🚫 You need permission: {', '.join(f'`{p}`' for p in error.missing_permissions)}.", ephemeral=True)
    elif isinstance(error, app_commands.BotMissingPermissions): await interaction.response.send_message(f"🤖 Bot needs permission: {', '.join(f'`{p}`' for p in error.missing_permissions)}.", ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure): await interaction.response.send_message("🚫 You do not have permission to use this command.", ephemeral=True)
    elif isinstance(error, app_commands.CommandInvokeError):
        original = error.original
        if isinstance(original, discord.Forbidden): await interaction.response.send_message(f"🚫 Discord Permissions Error (often role hierarchy).", ephemeral=True)
        else:
            print(f'Unhandled error in app command {interaction.command.name if interaction.command else "Unknown"}: {original}')
            message = "⚙️ An unexpected error occurred."
            if not interaction.response.is_done(): await interaction.response.send_message(message, ephemeral=True)
            else: await interaction.followup.send(message, ephemeral=True)
    else:
        print(f'Unhandled app command error type: {type(error).__name__} - {error}')
        message = "🤔 An unknown error occurred."
        if not interaction.response.is_done(): await interaction.response.send_message(message, ephemeral=True)
        else: await interaction.followup.send(message, ephemeral=True)
# Add the error handler to the command tree
bot.tree.on_error = on_app_command_error

# --- Start of Part 2: Core Role Management Slash Commands ---

# --- Slash Command: Create Role ---
@bot.tree.command(name="createrole", description="Creates a new role in the server.")
@app_commands.describe(role_name="The exact name for the new role.")
@app_commands.checks.has_permissions(manage_roles=True) # User permission check
@app_commands.checks.bot_has_permissions(manage_roles=True) # Bot permission check
async def slash_createrole(interaction: discord.Interaction, role_name: str):
    """Slash command to create a new role."""
    guild = interaction.guild
    # Defer response first, as role creation might take time
    await interaction.response.defer(ephemeral=True) # ephemeral=True hides "Bot is thinking..."

    if not guild:
        await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
        return

    existing_role = get(guild.roles, name=role_name)
    if existing_role:
        await interaction.followup.send(f"⚠️ A role named **{role_name}** already exists!", ephemeral=True)
        return

    if len(role_name) > 100:
        await interaction.followup.send("❌ Role name cannot be longer than 100 characters.", ephemeral=True)
        return

    try:
        # Create the role with default permissions and color
        new_role = await guild.create_role(name=role_name, reason=f"Created by {interaction.user} via slash command.")
        # Use followup after deferring, make success message visible
        await interaction.followup.send(f"✅ Successfully created role: {new_role.mention}", ephemeral=False)
    except discord.Forbidden:
        # BotMissingPermissions check should ideally catch this, but included as fallback
        await interaction.followup.send("🚫 **Bot Permission Error:** I don't have permission to create roles.", ephemeral=True)
    except discord.HTTPException as e:
        print(f"Error in /createrole (HTTP): {e}")
        await interaction.followup.send(f"⚙️ An HTTP error occurred during role creation: {e}", ephemeral=True)
    except Exception as e:
        print(f"Error in /createrole: {e}")
        await interaction.followup.send(f"⚙️ An unexpected error occurred during role creation: {e}", ephemeral=True)


# --- Slash Command: Delete Role ---
@bot.tree.command(name="deleterole", description="Deletes an existing role by its exact name.")
@app_commands.describe(role_name="The exact name of the role to delete.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_deleterole(interaction: discord.Interaction, role_name: str):
    """Slash command to delete a role."""
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True)

    if not guild:
        await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
        return

    # Find the role by name (case-sensitive)
    role_to_delete = get(guild.roles, name=role_name)

    if not role_to_delete:
        await interaction.followup.send(f"❓ Could not find a role named **{role_name}**. Remember, names are case-sensitive.", ephemeral=True)
        return

    # Safety Checks
    if role_to_delete == guild.default_role: # @everyone role
        await interaction.followup.send("🚫 Cannot delete the `@everyone` role.", ephemeral=True)
        return
    if role_to_delete >= guild.me.top_role and guild.me != guild.owner: # Hierarchy check
        await interaction.followup.send(f"🚫 **Hierarchy Error:** I cannot delete {role_to_delete.mention} as it's higher than or equal to my role.", ephemeral=True)
        return
    if role_to_delete.is_integration() or role_to_delete.is_premium_subscriber() or role_to_delete.is_bot_managed(): # Managed roles
         await interaction.followup.send(f"⚠️ Cannot delete {role_to_delete.mention} as it's managed by Discord or an integration.", ephemeral=True)
         return

    try:
        role_name_saved = role_to_delete.name
        await role_to_delete.delete(reason=f"Deleted by {interaction.user} via slash command.")
        await interaction.followup.send(f"✅ Successfully deleted role: **{role_name_saved}**", ephemeral=False) # Make confirmation visible
    except discord.Forbidden:
        await interaction.followup.send(f"🚫 **Bot Permission Error:** I lack permission to delete the role **{role_name}**. Check hierarchy.", ephemeral=True)
    except discord.HTTPException as e:
        print(f"Error in /deleterole (HTTP): {e}")
        await interaction.followup.send(f"⚙️ An HTTP error occurred: {e}", ephemeral=True)
    except Exception as e:
        print(f"Error in /deleterole: {e}")
        await interaction.followup.send(f"⚙️ An unexpected error occurred: {e}", ephemeral=True)


# --- Slash Command: Give Role ---
@bot.tree.command(name="giverole", description="Assigns a role to a specified member.")
@app_commands.describe(user="The user to give the role to.", role_name="The exact name of the role to assign.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_giverole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    """Slash command to give a role to a member."""
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True)

    if not guild:
        await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
        return

    # Find the role by name (case-sensitive)
    role_to_give = get(guild.roles, name=role_name)

    if not role_to_give:
        await interaction.followup.send(f"❓ Could not find a role named **{role_name}**. Check spelling and case.", ephemeral=True)
        return

    # Hierarchy Check: Bot vs Role to Give
    if role_to_give >= guild.me.top_role and guild.me != guild.owner:
        await interaction.followup.send(f"🚫 **Hierarchy Error:** I cannot assign {role_to_give.mention} as it's higher than or equal to my role.", ephemeral=True)
        return
    # Hierarchy Check: Command User vs Role to Give
    if isinstance(interaction.user, discord.Member): # Ensure command user is a member before checking roles
        if role_to_give >= interaction.user.top_role and interaction.user != guild.owner:
            await interaction.followup.send(f"🚫 **Permission Denied:** You cannot assign {role_to_give.mention} as it's higher than or equal to your own highest role.", ephemeral=True)
            return
    # Check if member already has the role
    if role_to_give in user.roles:
        await interaction.followup.send(f"ℹ️ {user.mention} already has the role {role_to_give.mention}.", ephemeral=True)
        return

    try:
        await user.add_roles(role_to_give, reason=f"Role added by {interaction.user} via slash command.")
        await interaction.followup.send(f"✅ Successfully gave the role {role_to_give.mention} to {user.mention}.", ephemeral=False) # Visible confirmation
    except discord.Forbidden:
        await interaction.followup.send(f"🚫 **Bot Permission Error:** I lack permission to assign the role {role_to_give.mention}.", ephemeral=True)
    except discord.HTTPException as e:
        print(f"Error in /giverole (HTTP): {e}")
        await interaction.followup.send(f"⚙️ An HTTP error occurred: {e}", ephemeral=True)
    except Exception as e:
        print(f"Error in /giverole: {e}")
        await interaction.followup.send(f"⚙️ An unexpected error occurred: {e}", ephemeral=True)


# --- Slash Command: Take Role ---
@bot.tree.command(name="takerole", description="Removes a role from a specified member.")
@app_commands.describe(user="The user to remove the role from.", role_name="The exact name of the role to remove.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_takerole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    """Slash command to remove a role from a member."""
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True)

    if not guild:
        await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
        return

    # Find the role by name (case-sensitive)
    role_to_take = get(guild.roles, name=role_name)

    if not role_to_take:
        await interaction.followup.send(f"❓ Could not find a role named **{role_name}**. Check spelling and case.", ephemeral=True)
        return

    # Hierarchy Check: Bot vs Role to Take
    if role_to_take >= guild.me.top_role and guild.me != guild.owner:
        await interaction.followup.send(f"🚫 **Hierarchy Error:** I cannot remove {role_to_take.mention} as it's higher than or equal to my role.", ephemeral=True)
        return
    # Hierarchy Check: Command User vs Role to Take
    if isinstance(interaction.user, discord.Member):
        if role_to_take >= interaction.user.top_role and interaction.user != guild.owner:
            await interaction.followup.send(f"🚫 **Permission Denied:** You cannot remove {role_to_take.mention} as it's higher than or equal to your own highest role.", ephemeral=True)
            return
    # Check if member actually has the role
    if role_to_take not in user.roles:
        await interaction.followup.send(f"ℹ️ {user.mention} doesn't have the role {role_to_take.mention}.", ephemeral=True)
        return
    # Prevent removing integration/booster roles via this command
    if role_to_take.is_integration() or role_to_take.is_premium_subscriber() or role_to_take.is_bot_managed():
         await interaction.followup.send(f"⚠️ Cannot remove {role_to_take.mention} via this command as it's managed by Discord or an integration.", ephemeral=True)
         return

    try:
        await user.remove_roles(role_to_take, reason=f"Role removed by {interaction.user} via slash command.")
        await interaction.followup.send(f"✅ Successfully removed the role {role_to_take.mention} from {user.mention}.", ephemeral=False) # Visible confirmation
    except discord.Forbidden:
         await interaction.followup.send(f"🚫 **Bot Permission Error:** I lack permission to remove the role {role_to_take.mention}.", ephemeral=True)
    except discord.HTTPException as e:
        print(f"Error in /takerole (HTTP): {e}")
        await interaction.followup.send(f"⚙️ An HTTP error occurred: {e}", ephemeral=True)
    except Exception as e:
        print(f"Error in /takerole: {e}")
        await interaction.followup.send(f"⚙️ An unexpected error occurred: {e}", ephemeral=True)

# --- End of Part 2 ---
# --- Start of Part 3: Separator, Clear, and Help Slash Commands ---

# --- Slash Command: Create Separator Role ---
@bot.tree.command(name="createseparator", description="Creates a visual separator role.")
@app_commands.describe(label="The text to display inside the separator (e.g., '身分', '通知').")
@app_commands.checks.has_permissions(manage_roles=True) # User permission check
@app_commands.checks.bot_has_permissions(manage_roles=True) # Bot permission check
async def slash_createseparator(interaction: discord.Interaction, label: str):
    """Slash command to create a visual separator role."""
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True) # Defer immediately

    if not guild:
        await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
        return

    # --- Define the separator format ---
    separator_name = f"▲─────{label}─────" # Customize if needed
    if len(separator_name) > 100:
        await interaction.followup.send(f"❌ Error: The label '{label}' is too long, resulting name exceeds 100 characters.", ephemeral=True)
        return

    # Check if a role with this exact name already exists
    existing_role = get(guild.roles, name=separator_name)
    if existing_role:
        await interaction.followup.send(f"⚠️ A separator role named **{separator_name}** already exists!", ephemeral=True)
        return

    try:
        # Create the role with NO permissions and a subtle color
        new_role = await guild.create_role(
            name=separator_name,
            permissions=discord.Permissions.none(), # No permissions
            color=discord.Color.light_grey(), # Subtle color
            hoist=False, # Not displayed separately
            mentionable=False, # Not mentionable
            reason=f"Separator created by {interaction.user} via slash command."
        )
        # Send confirmation (visible to others with instruction)
        await interaction.followup.send(
            f"✅ Successfully created separator role: **{new_role.name}**\n"
            f"**重要:** 请前往 **服务器设置 -> 身份组**，手动将此身份组拖动到你想要的位置以实现视觉分隔！",
            ephemeral=False # Make instruction visible
        )
    except discord.Forbidden:
        await interaction.followup.send("🚫 **Bot Permission Error:** I don't have permission to create roles.", ephemeral=True)
    except discord.HTTPException as e:
        print(f"Error in /createseparator (HTTP): {e}")
        await interaction.followup.send(f"⚙️ An HTTP error occurred: {e}", ephemeral=True)
    except Exception as e:
        print(f"Error in /createseparator: {e}")
        await interaction.followup.send(f"⚙️ An unexpected error occurred: {e}", ephemeral=True)

# --- Slash Command: Clear Messages ---
# Use Range to enforce limits directly in the command definition
@bot.tree.command(name="clear", description="Deletes a specified number of messages in this channel (1-100).")
@app_commands.describe(amount="Number of messages to delete.")
@app_commands.checks.has_permissions(manage_messages=True) # User permission
@app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True) # Bot permission
async def slash_clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    """Slash command to clear messages."""
    channel = interaction.channel # Command is invoked in the target channel

    # Ensure it's a text channel where messages can be deleted
    if not isinstance(channel, discord.TextChannel):
         await interaction.response.send_message("This command can only be used in text channels.", ephemeral=True)
         return

    # Defer immediately, make it ephemeral
    await interaction.response.defer(ephemeral=True)
    try:
        # Purge the messages
        deleted_messages = await channel.purge(limit=amount)
        # Send ephemeral confirmation via followup
        await interaction.followup.send(f"✅ Successfully deleted {len(deleted_messages)} message(s).", ephemeral=True)
        # Optionally log to a mod log channel here if needed
    except discord.Forbidden:
        await interaction.followup.send("🚫 **Bot Permission Error:** I lack 'Manage Messages' or 'Read Message History' permission in this channel.", ephemeral=True)
    except discord.HTTPException as e:
        print(f"Error in /clear (HTTP): {e}")
        await interaction.followup.send(f"⚙️ An HTTP error occurred during message deletion: {e}", ephemeral=True)
    except Exception as e:
        print(f"Error in /clear: {e}")
        await interaction.followup.send(f"⚙️ An unexpected error occurred: {e}", ephemeral=True)

# --- Slash Command: Help ---
@bot.tree.command(name="help", description="Shows information about available commands.")
async def slash_help(interaction: discord.Interaction):
    """Provides help information via slash command."""
    # Using the embed structure from previous replies which lists all commands
    embed = discord.Embed(
        title="🤖 GJ Team Role Manager Bot Help",
        description="Here are the available slash commands:",
        color=discord.Color.purple()
    )
    # Combine Role Management and Moderation for the help embed
    embed.add_field(
        name="🛠️ Moderation & Management",
        value=("/createrole `role_name` - Creates a new standard role.\n"
               "/deleterole `role_name` - Deletes a role.\n"
               "/giverole `user` `role_name` - Assigns a role.\n"
               "/takerole `user` `role_name` - Removes a role.\n"
               "/createseparator `label` - Creates a visual separator role.\n"
               "/clear `amount` - Deletes messages (max 100).\n"
               "/warn `user` `[reason]` - Manually issues a warning.\n"
               "/unwarn `user` `[reason]` - Removes one warning."),
        inline=False
    )
    embed.add_field(
        name="ℹ️ Other",
        value="/help - Shows this message.",
        inline=False
    )
    embed.set_footer(text="<> = Required, [] = Optional. Admin permissions needed for most commands.")
    # Help message is usually ephemeral
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- End of Part 3 ---
# --- Start of Part 4: Warn/Unwarn Commands, Event Listeners, and Bot Run ---

# --- Slash Command: Manually Warn User ---
@bot.tree.command(name="warn", description="Manually issues a warning to a user.")
@app_commands.describe(
    user="The user to warn.",
    reason="The reason for the warning (optional)."
)
@app_commands.checks.has_permissions(kick_members=True) # Require Kick perms to warn
async def slash_warn(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    """Slash command to manually warn a user."""
    guild = interaction.guild
    author = interaction.user # The admin issuing the warning

    if not guild: await interaction.response.send_message("Server only.", ephemeral=True); return
    if user.bot: await interaction.response.send_message("Cannot warn bots.", ephemeral=True); return
    if user == author: await interaction.response.send_message("Cannot warn yourself.", ephemeral=True); return
    # Optional: Prevent warning users with higher roles than the issuer
    if isinstance(author, discord.Member) and isinstance(user, discord.Member):
         if user.top_role >= author.top_role and author != guild.owner:
             await interaction.response.send_message(f"🚫 Cannot warn {user.mention} (Role Hierarchy).", ephemeral=True); return

    await interaction.response.defer(ephemeral=False) # Defer but make warning embed visible

    user_id = user.id
    # Increment warning count
    user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
    warning_count = user_warnings[user_id]

    print(f"⚠️ Manual Warning: {author.name} warned {user.name}. Reason: {reason}. New count: {warning_count}/{KICK_THRESHOLD}")

    # Prepare embed for warning/kick message
    embed = discord.Embed(color=discord.Color.orange())
    embed.set_author(name=f"Warning issued by {author.display_name}", icon_url=author.display_avatar.url)
    embed.add_field(name="User Warned", value=user.mention, inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Current Warnings", value=f"{warning_count} / {KICK_THRESHOLD}", inline=False)
    embed.timestamp = discord.utils.utcnow()

    # Check if Kick Threshold is Reached
    if warning_count >= KICK_THRESHOLD:
        embed.title = "🚨 Warning Limit Reached - User Kicked 🚨"
        embed.color = discord.Color.red()
        embed.add_field(name="Action Taken", value="User Kicked from Server", inline=False)
        print(f"   Kick threshold reached for {user.name} due to manual warn.")

        bot_member = guild.me
        kick_allowed = False
        kick_fail_reason = "Unknown Error"

        # Check bot permissions and hierarchy BEFORE attempting kick
        if bot_member.guild_permissions.kick_members:
            if bot_member.top_role > user.top_role or bot_member == guild.owner:
                kick_allowed = True
            else:
                kick_fail_reason = "机器人身份组层级不足"
                print(f"   Kick Fail: Bot role not high enough to kick {user.name}.")
                embed.add_field(name="Kick Status", value=f"Failed ({kick_fail_reason})", inline=False)
        else:
            kick_fail_reason = "机器人缺少“踢出成员”权限"
            print(f"   Kick Fail: Bot lacks 'Kick Members' permission.")
            embed.add_field(name="Kick Status", value=f"Failed ({kick_fail_reason})", inline=False)

        # Attempt Kick if allowed
        if kick_allowed:
            try:
                kick_dm_reason = f"你因累计达到 {KICK_THRESHOLD} 次警告（最后一次由 {author.display_name} 发出，原因：{reason}）而被踢出服务器 **{guild.name}**。"
                try:
                    await user.send(kick_dm_reason)
                    print(f"   Sent kick DM to {user.name}.")
                except Exception as dm_err: print(f"   Could not send kick DM to {user.name}: {dm_err}")

                await user.kick(reason=f"警告达到 {KICK_THRESHOLD} 次 (手动警告 by {author.name}: {reason})")
                print(f"   Kicked {user.name}.")
                embed.add_field(name="Kick Status", value="Success", inline=False)
                # Reset warnings ONLY if kick was successful
                user_warnings[user_id] = 0
            except discord.Forbidden:
                 print(f"   Kick Error: Bot lacked Discord perms/hierarchy during kick attempt on {user.name}.")
                 embed.add_field(name="Kick Status", value="Failed (权限/层级不足)", inline=False)
            except Exception as kick_error:
                print(f"   Kick Error: {kick_error}")
                embed.add_field(name="Kick Status", value=f"Failed ({kick_error})", inline=False)
    else:
        embed.title = "⚠️ Manual Warning Issued ⚠️"
        embed.add_field(name="Next Step", value=f"达到 {KICK_THRESHOLD} 次警告将会被踢出。", inline=False)

    # Send the confirmation embed to the channel
    await interaction.followup.send(embed=embed)


# --- Slash Command: Remove Warning ---
@bot.tree.command(name="unwarn", description="Removes the most recent warning from a user.")
@app_commands.describe(
    user="The user to remove a warning from.",
    reason="The reason for removing the warning (optional)."
)
@app_commands.checks.has_permissions(kick_members=True) # Require Kick perms to unwarn
async def slash_unwarn(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    """Slash command to remove a warning from a user."""
    guild = interaction.guild
    author = interaction.user

    if not guild: await interaction.response.send_message("...", ephemeral=True); return
    if user.bot: await interaction.response.send_message("Bots don't have warnings.", ephemeral=True); return

    user_id = user.id
    current_warnings = user_warnings.get(user_id, 0)

    if current_warnings <= 0:
        await interaction.response.send_message(f"{user.mention} currently has no warnings to remove.", ephemeral=True)
        return

    # Decrement warning count
    user_warnings[user_id] = current_warnings - 1
    new_warning_count = user_warnings[user_id]

    print(f"✅ Unwarn: {author.name} removed a warning from {user.name}. Reason: {reason}. New count: {new_warning_count}/{KICK_THRESHOLD}")

    # Prepare confirmation embed
    embed = discord.Embed(title="✅ Warning Removed ✅", color=discord.Color.green())
    embed.set_author(name=f"Action by {author.display_name}", icon_url=author.display_avatar.url)
    embed.add_field(name="User", value=user.mention, inline=False)
    embed.add_field(name="Reason for Removal", value=reason, inline=False)
    embed.add_field(name="New Warning Count", value=f"{new_warning_count} / {KICK_THRESHOLD}", inline=False)
    embed.timestamp = discord.utils.utcnow()

    # Send confirmation (visible)
    await interaction.response.send_message(embed=embed)


# --- Event: Member Join - Assign Separator Roles & Welcome ---
@bot.event
async def on_member_join(member: discord.Member):
    """Automatically assigns specific pre-existing separator roles and sends a welcome message."""
    guild = member.guild
    print(f'[+] {member.name} ({member.id}) joined {guild.name}')

    # --- Define the EXACT names of your pre-existing separator roles ---
    # !!! IMPORTANT: Replace these with the exact names you created in your server !!!
    separator_role_names_to_assign = [
        "▲─────身分─────",   # <-- 替换!
        "▲─────通知─────",   # <-- 替换!
        "▲─────其他─────"    # <-- 替换!
        # Add more separator role names here if needed
    ]

    roles_to_add = []
    roles_failed = []

    # --- Assign Separator Roles ---
    for role_name in separator_role_names_to_assign:
        role = get(guild.roles, name=role_name)
        if role:
            if role < guild.me.top_role or guild.me == guild.owner: roles_to_add.append(role)
            else: roles_failed.append(f"{role_name} (层级不足)")
        else: roles_failed.append(f"{role_name} (未找到!)")

    if roles_to_add:
        try:
            await member.add_roles(*roles_to_add, reason="Auto-assigned separator roles on join")
            print(f"✅ Assigned {len(roles_to_add)} separators to {member.name}.")
        except Exception as e:
            print(f"❌ Error assigning roles to {member.name}: {e}")
            roles_failed.extend([f"{r.name} ({type(e).__name__})" for r in roles_to_add])

    if roles_failed: print(f"‼️ Could not assign for {member.name}: {', '.join(roles_failed)}")

    # --- (Optional) Send Welcome Message ---
    # !!! IMPORTANT: Replace channel IDs below !!!
    welcome_channel_id = 123456789012345678      # <--- 替换! 欢迎频道ID
    rules_channel_id = 123456789012345679        # <--- 替换! 规则频道ID
    roles_info_channel_id = 123456789012345680   # <--- 替换! 身份组介绍频道ID
    verification_channel_id = 123456789012345681 # <--- 替换! 实力认证频道ID

    welcome_channel = guild.get_channel(welcome_channel_id)
    if welcome_channel and isinstance(welcome_channel, discord.TextChannel):
        try:
            embed = discord.Embed(
                title=f"🎉 欢迎来到 {guild.name}! 🎉",
                description=f"你好 {member.mention}! 很高兴你能加入 **GJ Team**！\n\n"
                            f"👇 **为了更好的体验, 请先:**\n"
                            f"- 阅读服务器规则: <#{rules_channel_id}>\n"
                            f"- 了解身份组信息: <#{roles_info_channel_id}>\n"
                            f"- 认证你的TSB实力: <#{verification_channel_id}>\n"
                            f"\n祝你在 GJ Team 玩得愉快!",
                color=discord.Color.blue() # Customize color
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"你是服务器的第 {guild.member_count} 位成员！")
            await welcome_channel.send(embed=embed)
            print(f"Sent welcome message for {member.name}.")
        except Exception as e: print(f"❌ Error sending welcome message: {e}")
    elif welcome_channel_id != 123456789012345678: # Only warn if ID was changed
        print(f"⚠️ Welcome channel {welcome_channel_id} not found.")


# --- Event: On Message - Handles User Spam, Bot Spam, and Commands ---
@bot.event
async def on_message(message: discord.Message):
    # --- Basic Checks ---
    if not message.guild: return # Ignore DMs
    if message.author.id == bot.user.id: return # Ignore self

    # --- Bot Spam Detection Logic ---
    if message.author.bot:
        bot_author_id = message.author.id
        now_bot = datetime.datetime.now(datetime.timezone.utc)
        bot_message_timestamps.setdefault(bot_author_id, [])
        bot_message_timestamps[bot_author_id].append(now_bot)
        time_limit_bot = now_bot - datetime.timedelta(seconds=BOT_SPAM_TIME_WINDOW_SECONDS)
        bot_message_timestamps[bot_author_id] = [ts for ts in bot_message_timestamps[bot_author_id] if ts > time_limit_bot]

        bot_message_count = len(bot_message_timestamps[bot_author_id])
        if bot_message_count >= BOT_SPAM_COUNT_THRESHOLD:
            print(f"🚨 BOT Spam Detected: {message.author} ({bot_author_id}) in #{message.channel.name}")
            bot_message_timestamps[bot_author_id] = [] # Reset timestamps for this bot

            # --- Action: Alert Mods and Delete Messages ---
            mod_mentions = " ".join([f"<@&{role_id}>" for role_id in MOD_ALERT_ROLE_IDS]) # !!! Ensure MOD_ALERT_ROLE_IDS is defined correctly at top !!!
            alert_message = (
                f"🚨 **检测到机器人刷屏！** 🚨\n"
                f"机器人: {message.author.mention} (`{message.author.name}` ID: `{bot_author_id}`)\n"
                f"频道: {message.channel.mention}\n"
                f"时间: {discord.utils.format_dt(now_bot, style='F')}\n"
                f"{mod_mentions} 请管理员关注并进行调查！"
            )
            try: await message.channel.send(alert_message); print(f"   Sent bot spam alert to #{message.channel.name}")
            except Exception as alert_err: print(f"   Error sending bot spam alert: {alert_err}")

            deleted_count = 0
            if message.channel.permissions_for(message.guild.me).manage_messages:
                print(f"   Attempting to delete recent messages from bot {message.author.name}...")
                try:
                    # Fetch recent messages and delete only the bot's messages
                    async for msg in message.channel.history(limit=BOT_SPAM_COUNT_THRESHOLD * 2, after=time_limit_bot - datetime.timedelta(seconds=2)):
                        if msg.author.id == bot_author_id:
                            try: await msg.delete(); deleted_count += 1
                            except Exception: pass # Ignore single deletion errors
                    print(f"   Deleted {deleted_count} messages from spamming bot {message.author.name}.")
                    if deleted_count > 0: await message.channel.send(f"🧹 已自动清理 {deleted_count} 条来自 {message.author.mention} 的刷屏消息。", delete_after=15)
                except Exception as del_err: print(f"   Error during bot message deletion: {del_err}")
            else: print("   Bot lacks 'Manage Messages' permission, cannot delete bot spam.")
        return # Stop processing for bot messages

    # --- User Spam Detection Logic (Only if message.author is NOT a bot) ---
    author_id = message.author.id
    now_user = datetime.datetime.now(datetime.timezone.utc)
    member = message.guild.get_member(author_id) # Fetch member object
    if member and message.channel.permissions_for(member).manage_messages: # Ignore mods for spam
        # if message.content.startswith(COMMAND_PREFIX): await bot.process_commands(message) # Process commands if needed
        return

    user_message_timestamps.setdefault(author_id, [])
    user_warnings.setdefault(author_id, 0)
    user_message_timestamps[author_id].append(now_user)
    time_limit_user = now_user - datetime.timedelta(seconds=SPAM_TIME_WINDOW_SECONDS)
    user_message_timestamps[author_id] = [ts for ts in user_message_timestamps[author_id] if ts > time_limit_user]

    message_count = len(user_message_timestamps[author_id])
    if message_count >= SPAM_COUNT_THRESHOLD:
        print(f"🚨 User Spam detected: {message.author} ({author_id}) in #{message.channel.name}")
        user_warnings[author_id] += 1
        warning_count = user_warnings[author_id]
        print(f"   User warnings: {warning_count}/{KICK_THRESHOLD}")
        user_message_timestamps[author_id] = [] # Reset user timestamps

        if warning_count >= KICK_THRESHOLD:
            print(f"   Kick threshold reached for {message.author}.")
            if member: # Kick if possible
                bot_member = message.guild.me; kick_reason = f"自动踢出：刷屏警告达到 {KICK_THRESHOLD} 次。"
                if bot_member.guild_permissions.kick_members and (bot_member.top_role > member.top_role or bot_member == message.guild.owner):
                    try:
                        try: await member.send(f"你已被踢出服务器 **{message.guild.name}**。\n原因：**{kick_reason}**")
                        except Exception as dm_err: print(f"   Could not send kick DM to {member.name}: {dm_err}")
                        await member.kick(reason=kick_reason)
                        print(f"   Kicked {member.name}."); await message.channel.send(f"👢 {member.mention} 已被自动踢出，原因：刷屏警告次数过多。")
                        user_warnings[author_id] = 0 # Reset warnings
                    except Exception as kick_err: print(f"   Error during kick: {kick_err}"); await message.channel.send(f"⚙️ 踢出 {member.mention} 时发生错误。")
                else: print(f"   Bot lacks perms/hierarchy to kick {member.name}."); await message.channel.send(f"⚠️ 无法踢出 {member.mention} (权限/层级不足)。")
            else: print(f"   Could not get Member object for {author_id} to kick.")
        else: # Send warning
            try: await message.channel.send(f"⚠️ {message.author.mention}，请减缓发言！({warning_count}/{KICK_THRESHOLD} 警告)", delete_after=15)
            except Exception as warn_err: print(f"   Error sending warning: {warn_err}")

    # Process legacy prefix commands if the message wasn't spam or from ignored user
    # If you only use slash commands, this block can be removed.
    # if message.content.startswith(COMMAND_PREFIX):
    #    await bot.process_commands(message)


# --- Placeholder for Your Highly Customized Assignment Logic ---
# Add more custom @bot.tree.command() or @bot.listen() functions here


# --- Run the Bot ---
if __name__ == "__main__":
    print("Starting bot...")
    try:
        # This runs the bot using the token loaded from the environment variable
        bot.run(BOT_TOKEN)
    except discord.LoginFailure: print("❌ FATAL ERROR: Login failed. Invalid DISCORD_BOT_TOKEN.")
    except discord.PrivilegedIntentsRequired: print("❌ FATAL ERROR: Privileged Intents required but not enabled in Developer Portal.")
    except Exception as e: print(f"❌ FATAL ERROR during startup: {e}")


# --- End of Complete Code ---