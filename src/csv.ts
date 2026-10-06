/** CSV for browser-side exports: every cell quoted when it holds a comma, quote or line
 *  break, CRLF line endings, and a byte-order mark so Excel opens UTF-8 names correctly. */
const csvCell = (value: unknown) => {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

export const toCsv = (rows: unknown[][]) => "﻿" + rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
