# database.py
import sqlite3
import os
from typing import Dict, Any, Optional, List, Tuple # 确保从 typing 导入这些

# 数据库文件名，将与 role_manager_bot.py 在同一目录或指定路径
# 如果你想放在特定数据文件夹，可以修改，例如：
# SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# DATABASE_FILE = os.path.join(SCRIPT_DIR, "data", "gjteam_bot.db")
# 并确保 "data" 文件夹存在
DATABASE_FILE = "gjteam_bot.db"

# --- 表名常量 ---
TABLE_USER_BALANCES = "user_balances"
TABLE_SHOP_ITEMS = "shop_items"
TABLE_GUILD_ECONOMY_SETTINGS = "guild_economy_settings"
TABLE_GUILD_KNOWLEDGE_BASE = "guild_knowledge_base"
# 你可以为其他需要持久化的数据添加更多表名常量

def get_db_connection() -> sqlite3.Connection:
    """获取并返回一个数据库连接对象。"""
    # 检查数据库文件所在目录是否存在，如果不存在则创建
    db_dir = os.path.dirname(os.path.abspath(DATABASE_FILE))
    if db_dir and not os.path.exists(db_dir): # 检查 db_dir 是否为空（如果DATABASE_FILE只是文件名）
        try:
            os.makedirs(db_dir)
            print(f"[Database] Created directory for database: {db_dir}")
        except OSError as e:
            print(f"[Database Error] Could not create directory {db_dir}: {e}")
            # 如果目录创建失败，连接到当前目录的数据库文件可能仍会工作，或者会报错

    conn = sqlite3.connect(DATABASE_FILE, timeout=10) # 添加超时
    conn.row_factory = sqlite3.Row # 允许通过列名访问数据
    # 启用外键约束 (如果你的表之间有外键关系)
    # conn.execute("PRAGMA foreign_keys = ON")
    return conn

def initialize_database():
    """初始化数据库，创建所有必要的表（如果它们尚不存在）。"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # --- 用户余额表 ---
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {TABLE_USER_BALANCES} (
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        balance INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )
    """)

    # --- 商店物品表 ---
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {TABLE_SHOP_ITEMS} (
        guild_id INTEGER NOT NULL,
        item_slug TEXT NOT NULL,
        name TEXT NOT NULL,
        price INTEGER NOT NULL,
        description TEXT,
        role_id INTEGER,
        stock INTEGER DEFAULT -1, -- -1 for infinite
        purchase_message TEXT,
        PRIMARY KEY (guild_id, item_slug)
    )
    """)

    # --- 服务器经济设置表 ---
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {TABLE_GUILD_ECONOMY_SETTINGS} (
        guild_id INTEGER PRIMARY KEY,
        chat_earn_amount INTEGER,
        chat_earn_cooldown INTEGER
    )
    """)

    # --- 服务器 AI 知识库表 ---
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {TABLE_GUILD_KNOWLEDGE_BASE} (
        guild_id INTEGER NOT NULL,
        entry_order INTEGER NOT NULL, 
        entry_text TEXT NOT NULL,
        PRIMARY KEY (guild_id, entry_order) 
    )
    """)
    
    # --- 你可以在这里为其他功能添加更多的 CREATE TABLE IF NOT EXISTS 语句 ---
    # 例如: AI DEP 频道配置, FAQ, AI 豁免列表等

    conn.commit()
    conn.close()
    print("[Database] 数据库初始化完毕 (所有核心表已创建/确认存在)。")

# =========================================
# == 经济系统 - 余额操作
# =========================================
def db_get_user_balance(guild_id: int, user_id: int, default_balance: int) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT balance FROM {TABLE_USER_BALANCES} WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    row = cursor.fetchone()
    conn.close()
    return row["balance"] if row else default_balance

def db_update_user_balance(guild_id: int, user_id: int, amount: int, is_delta: bool = True, default_balance: int = 0) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        current_balance = db_get_user_balance(guild_id, user_id, default_balance)
        new_balance = (current_balance + amount) if is_delta else amount
        if new_balance < 0: return False

        cursor.execute(f"""
        INSERT INTO {TABLE_USER_BALANCES} (guild_id, user_id, balance) VALUES (?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = excluded.balance
        """, (guild_id, user_id, new_balance))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"[DB Economy Error] 更新用户余额失败 (guild: {guild_id}, user: {user_id}): {e}")
        return False
    finally:
        conn.close()

def db_get_leaderboard(guild_id: int, limit: int) -> List[Tuple[int, int]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT user_id, balance FROM {TABLE_USER_BALANCES} WHERE guild_id = ? ORDER BY balance DESC LIMIT ?", (guild_id, limit))
    leaderboard = cursor.fetchall()
    conn.close()
    return leaderboard

# =========================================
# == 经济系统 - 服务器设置
# =========================================
def db_get_guild_chat_earn_config(guild_id: int, default_amount: int, default_cooldown: int) -> Dict[str, int]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT chat_earn_amount, chat_earn_cooldown FROM {TABLE_GUILD_ECONOMY_SETTINGS} WHERE guild_id = ?", (guild_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row["chat_earn_amount"] is not None and row["chat_earn_cooldown"] is not None:
        return {"amount": row["chat_earn_amount"], "cooldown": row["chat_earn_cooldown"]}
    return {"amount": default_amount, "cooldown": default_cooldown}

def db_set_guild_chat_earn_config(guild_id: int, amount: int, cooldown: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"""
        INSERT INTO {TABLE_GUILD_ECONOMY_SETTINGS} (guild_id, chat_earn_amount, chat_earn_cooldown) VALUES (?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET chat_earn_amount = excluded.chat_earn_amount, chat_earn_cooldown = excluded.chat_earn_cooldown
        """, (guild_id, amount, cooldown))
        conn.commit()
    except sqlite3.Error as e:
        print(f"[DB Economy Error] 设置服务器聊天赚钱配置失败 (guild: {guild_id}): {e}")
    finally:
        conn.close()

# =========================================
# == 经济系统 - 商店操作
# =========================================
def db_get_shop_items(guild_id: int) -> Dict[str, Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT item_slug, name, price, description, role_id, stock, purchase_message FROM {TABLE_SHOP_ITEMS} WHERE guild_id = ?", (guild_id,))
    items = {row["item_slug"]: dict(row) for row in cursor.fetchall()}
    conn.close()
    return items

def db_get_shop_item(guild_id: int, item_slug: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT item_slug, name, price, description, role_id, stock, purchase_message FROM {TABLE_SHOP_ITEMS} WHERE guild_id = ? AND item_slug = ?", (guild_id, item_slug))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def db_add_shop_item(guild_id: int, item_slug: str, name: str, price: int, description: Optional[str],
                       role_id: Optional[int], stock: int, purchase_message: Optional[str]) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"""
        INSERT INTO {TABLE_SHOP_ITEMS} (guild_id, item_slug, name, price, description, role_id, stock, purchase_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (guild_id, item_slug, name, price, description, role_id, stock, purchase_message))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        print(f"[DB Economy Error] 添加商店物品失败 (guild: {guild_id}, slug: {item_slug}): 可能物品已存在。")
        return False
    except sqlite3.Error as e:
        print(f"[DB Economy Error] 添加商店物品失败 (guild: {guild_id}, slug: {item_slug}): {e}")
        return False
    finally:
        conn.close()

def db_remove_shop_item(guild_id: int, item_slug: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"DELETE FROM {TABLE_SHOP_ITEMS} WHERE guild_id = ? AND item_slug = ?", (guild_id, item_slug))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"[DB Economy Error] 移除商店物品失败 (guild: {guild_id}, slug: {item_slug}): {e}")
        return False
    finally:
        conn.close()

def db_update_shop_item_stock(guild_id: int, item_slug: str, new_stock: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 确保新库存不为负，除非是-1（无限）
        if new_stock < -1: new_stock = 0 
        cursor.execute(f"UPDATE {TABLE_SHOP_ITEMS} SET stock = ? WHERE guild_id = ? AND item_slug = ?", (new_stock, guild_id, item_slug))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"[DB Economy Error] 更新商店物品库存失败 (guild: {guild_id}, slug: {item_slug}): {e}")
        return False
    finally:
        conn.close()

def db_edit_shop_item(guild_id: int, item_slug: str, updates: Dict[str, Any]) -> bool:
    if not updates: return False
    set_clauses = [f"{key} = ?" for key in updates.keys() if key in ["name", "price", "description", "role_id", "stock", "purchase_message"]]
    if not set_clauses: return False # 没有有效的更新字段
    
    values = [updates[key] for key in updates.keys() if key in ["name", "price", "description", "role_id", "stock", "purchase_message"]]
    values.extend([guild_id, item_slug])
    
    sql = f"UPDATE {TABLE_SHOP_ITEMS} SET {', '.join(set_clauses)} WHERE guild_id = ? AND item_slug = ?"
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, tuple(values))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"[DB Economy Error] 编辑商店物品失败 (guild: {guild_id}, slug: {item_slug}): {e}")
        return False
    finally:
        conn.close()

# =========================================
# == AI 知识库操作
# =========================================
def db_get_knowledge_base(guild_id: int) -> List[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT entry_text FROM {TABLE_GUILD_KNOWLEDGE_BASE} WHERE guild_id = ? ORDER BY entry_order ASC", (guild_id,))
    entries = [row["entry_text"] for row in cursor.fetchall()]
    conn.close()
    return entries

def db_add_knowledge_base_entry(guild_id: int, entry_text: str, max_entries: int) -> Tuple[bool, str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT COUNT(*) as count FROM {TABLE_GUILD_KNOWLEDGE_BASE} WHERE guild_id = ?", (guild_id,))
        current_count = cursor.fetchone()["count"]
        if current_count >= max_entries:
            return False, "知识库已满。"

        cursor.execute(f"SELECT MAX(entry_order) as max_order FROM {TABLE_GUILD_KNOWLEDGE_BASE} WHERE guild_id = ?", (guild_id,))
        max_order_row = cursor.fetchone()
        next_order = (max_order_row["max_order"] if max_order_row and max_order_row["max_order"] is not None else 0) + 1
        
        cursor.execute(f"INSERT INTO {TABLE_GUILD_KNOWLEDGE_BASE} (guild_id, entry_order, entry_text) VALUES (?, ?, ?)",
                       (guild_id, next_order, entry_text))
        conn.commit()
        return True, "添加成功。"
    except sqlite3.Error as e:
        print(f"[DB KB Error] 添加知识库条目失败 (guild: {guild_id}): {e}")
        conn.rollback()
        return False, f"数据库错误: {e}"
    finally:
        conn.close()

def db_remove_knowledge_base_entry_by_order(guild_id: int, entry_order_to_remove: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        conn.execute("BEGIN")
        cursor.execute(f"DELETE FROM {TABLE_GUILD_KNOWLEDGE_BASE} WHERE guild_id = ? AND entry_order = ?",
                       (guild_id, entry_order_to_remove))
        if cursor.rowcount == 0:
            conn.rollback()
            return False
        cursor.execute(f"UPDATE {TABLE_GUILD_KNOWLEDGE_BASE} SET entry_order = entry_order - 1 WHERE guild_id = ? AND entry_order > ?",
                       (guild_id, entry_order_to_remove))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"[DB KB Error] 按序号移除知识库条目失败 (guild: {guild_id}, order: {entry_order_to_remove}): {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def db_clear_knowledge_base(guild_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"DELETE FROM {TABLE_GUILD_KNOWLEDGE_BASE} WHERE guild_id = ?", (guild_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"[DB KB Error] 清空知识库失败 (guild: {guild_id}): {e}")
        return False
    finally:
        conn.close()

# --- 在文件末尾，可以添加一个初次运行时创建数据库文件的检查 ---
if __name__ == "__main__":
    # 这个 __main__ 块只会在直接运行 database.py 时执行，
    # 而不是在被 role_manager_bot.py导入时执行。
    # 这对于测试数据库连接或手动初始化很有用。
    print("database.py 被直接运行。正在尝试初始化数据库...")
    initialize_database()
    print("数据库初始化（如果需要）已完成。")
else:
    # 当被导入时，检查并初始化数据库（如果主程序还没做）
    # 更好的做法是在主程序的 on_ready 中调用 initialize_database()
    # 这里可以留空，或者只做一个简单的打印表明被导入
    # print("[Database] database.py 模块已加载。")
    pass