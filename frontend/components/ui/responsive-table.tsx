import type { ReactNode } from "react";

export interface TableColumn<T> {
  key: string;
  label: string;
  render: (row: T) => ReactNode;
  sortKey?: string;
}
export function ResponsiveTable<T>({
  caption,
  columns,
  rows,
  sort,
  direction,
  onSort,
  rowKey,
  onRow,
}: {
  caption: string;
  columns: TableColumn<T>[];
  rows: T[];
  sort?: string;
  direction?: "asc" | "desc";
  onSort?: (key: string) => void;
  rowKey: (row: T) => string;
  onRow?: (row: T) => void;
}) {
  return (
    <div className="table-wrap">
      <table>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col">
                {column.sortKey && onSort ? (
                  <button type="button" onClick={() => onSort(column.sortKey!)}>
                    {column.label}
                    {sort === column.sortKey ? (
                      <span aria-label={` sorted ${direction}`}>
                        {direction === "asc" ? " ↑" : " ↓"}
                      </span>
                    ) : null}
                  </button>
                ) : (
                  column.label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              className={onRow ? "clickable-row" : undefined}
              tabIndex={onRow ? 0 : undefined}
              onClick={() => onRow?.(row)}
              onKeyDown={(event) => {
                if (onRow && (event.key === "Enter" || event.key === " ")) {
                  event.preventDefault();
                  onRow(row);
                }
              }}
            >
              {columns.map((column) => (
                <td key={column.key} data-label={column.label}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
