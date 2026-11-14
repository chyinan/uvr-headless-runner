import type { ReactNode } from "react";

type Inline =
  | { kind: "text"; text: string }
  | { kind: "code"; text: string }
  | { kind: "strong"; children: Array<Inline> }
  | { kind: "link"; text: string; href: string };

type Block =
  | { kind: "p"; lines: Array<Array<Inline>> }
  | { kind: "ul"; items: Array<Array<Inline>> }
  | { kind: "ol"; items: Array<Array<Inline>> }
  | { kind: "pre"; text: string };

const LIST_ITEM = /^(\s*)([-*]|\d+[.)])\s+(.*)$/;

function parseInline(text: string): Array<Inline> {
  const nodes: Array<Inline> = [];
  let plain = "";
  let index = 0;
  const flush = () => {
    if (plain) nodes.push({ kind: "text", text: plain });
    plain = "";
  };
  while (index < text.length) {
    if (text[index] === "`") {
      const end = text.indexOf("`", index + 1);
      if (end > index) {
        flush();
        nodes.push({ kind: "code", text: text.slice(index + 1, end) });
        index = end + 1;
        continue;
      }
    }
    if (text.startsWith("**", index)) {
      const end = text.indexOf("**", index + 2);
      if (end > index) {
        flush();
        nodes.push({ kind: "strong", children: parseInline(text.slice(index + 2, end)) });
        index = end + 2;
        continue;
      }
    }
    if (text[index] === "[") {
      const labelEnd = text.indexOf("]", index + 1);
      if (labelEnd > index && text[labelEnd + 1] === "(") {
        const hrefEnd = text.indexOf(")", labelEnd + 2);
        const href = hrefEnd > labelEnd ? text.slice(labelEnd + 2, hrefEnd) : "";
        if (hrefEnd > labelEnd && /^https?:\/\//i.test(href)) {
          flush();
          nodes.push({ kind: "link", text: text.slice(index + 1, labelEnd), href });
          index = hrefEnd + 1;
          continue;
        }
      }
    }
    plain += text[index];
    index += 1;
  }
  flush();
  return nodes;
}

export function parseMarkdown(source: string): Array<Block> {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Array<Block> = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index] ?? "";
    if (line.startsWith("```")) {
      const body: Array<string> = [];
      index += 1;
      while (index < lines.length && !(lines[index] ?? "").startsWith("```")) {
        body.push(lines[index] ?? "");
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push({ kind: "pre", text: body.join("\n") });
      continue;
    }
    const item = line.match(LIST_ITEM);
    if (item) {
      const ordered = /\d/.test(item[2] ?? "");
      const items: Array<Array<Inline>> = [];
      while (index < lines.length) {
        const next = (lines[index] ?? "").match(LIST_ITEM);
        if (!next || /\d/.test(next[2] ?? "") !== ordered) break;
        items.push(parseInline(next[3] ?? ""));
        index += 1;
      }
      blocks.push({ kind: ordered ? "ol" : "ul", items });
      continue;
    }
    if (line.trim() === "") {
      index += 1;
      continue;
    }
    const paragraph: Array<string> = [];
    while (index < lines.length) {
      const next = lines[index] ?? "";
      if (next.trim() === "" || next.startsWith("```") || LIST_ITEM.test(next)) break;
      paragraph.push(next.replace(/^#{1,3}\s+/, ""));
      index += 1;
    }
    blocks.push({ kind: "p", lines: paragraph.map(parseInline) });
  }
  return blocks;
}

function renderInline(nodes: Array<Inline>, key: string): Array<ReactNode> {
  return nodes.map((node, index) => {
    const id = `${key}-${index}`;
    if (node.kind === "code") return <code key={id}>{node.text}</code>;
    if (node.kind === "strong") return <strong key={id}>{renderInline(node.children, id)}</strong>;
    if (node.kind === "link") {
      return <a key={id} href={node.href} target="_blank" rel="noreferrer">{node.text}</a>;
    }
    return <span key={id}>{node.text}</span>;
  });
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="md">
      {parseMarkdown(text).map((block, index) => {
        const key = `b${index}`;
        if (block.kind === "pre") return <pre key={key}><code>{block.text}</code></pre>;
        if (block.kind === "ul" || block.kind === "ol") {
          const Tag = block.kind;
          return (
            <Tag key={key}>
              {block.items.map((item, itemIndex) => <li key={`${key}-${itemIndex}`}>{renderInline(item, `${key}-${itemIndex}`)}</li>)}
            </Tag>
          );
        }
        return (
          <p key={key}>
            {block.lines.map((line, lineIndex) => (
              <span key={`${key}-${lineIndex}`}>
                {lineIndex > 0 ? <br /> : null}
                {renderInline(line, `${key}-${lineIndex}`)}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}
