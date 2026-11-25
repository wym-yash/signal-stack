import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function Markdown({ children }) {
  return (
    <div className="prose-brief">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{ a: ({ node, ...p }) => <a {...p} target="_blank" rel="noopener noreferrer" className="link" /> }}
      >
        {children || ""}
      </ReactMarkdown>
    </div>
  );
}
