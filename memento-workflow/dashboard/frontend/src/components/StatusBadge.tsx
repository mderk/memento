interface Props {
  status: string
}

export default function StatusBadge({ status }: Props) {
  return (
    <span className="status-badge" data-status={status}>
      <span className="status-dot" />
      {status}
    </span>
  )
}
