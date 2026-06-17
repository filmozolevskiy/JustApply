from . import connection


def get_outreach_settings(db_path=None):
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT target_russian_speakers, target_recruiters, short_connection_note FROM outreach_settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return {
            "target_russian_speakers": True,
            "target_recruiters": True,
            "short_connection_note": True,
        }
    return {
        "target_russian_speakers": bool(row["target_russian_speakers"]),
        "target_recruiters": bool(row["target_recruiters"]),
        "short_connection_note": bool(row["short_connection_note"]) if "short_connection_note" in row.keys() else True,
    }


def save_outreach_settings(
    target_russian_speakers: bool,
    target_recruiters: bool,
    short_connection_note: bool = True,
    db_path=None,
):
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO outreach_settings (id, target_russian_speakers, target_recruiters, short_connection_note)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            target_russian_speakers = excluded.target_russian_speakers,
            target_recruiters = excluded.target_recruiters,
            short_connection_note = excluded.short_connection_note
        """,
        (int(target_russian_speakers), int(target_recruiters), int(short_connection_note)),
    )
    conn.commit()
    conn.close()
    return {
        "target_russian_speakers": target_russian_speakers,
        "target_recruiters": target_recruiters,
        "short_connection_note": short_connection_note,
    }
