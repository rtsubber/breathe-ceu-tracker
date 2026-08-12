/**
 * Cloudflare Email Worker — Breathe CEU Email Forwarding
 *
 * Receives emails at *@sublettlabs.com via Cloudflare Email Routing,
 * parses them (including attachments), and POSTs to the Breathe API
 * webhook for auto-CEU logging.
 *
 * Deploy: wrangler deploy
 * Cloudflare Dashboard → Email Routing → Route to this Worker
 */

export default {
  async email(message, env, ctx) {
    const from = message.headers.get("from") || message.from || "";
    const to = message.headers.get("to") || message.to || "";
    const subject = message.headers.get("subject") || "";
    const messageId = message.headers.get("message-id") || "";

    let textBody = "";
    let htmlBody = "";
    const attachments = [];

    try {
      const rawEmail = await new Response(message.raw).text();
      const parts = parseMimeParts(rawEmail);

      for (const part of parts) {
        const decoded = decodePart(part);

        if (part.contentType === "text/plain" && !textBody) {
          textBody = decoded;
        } else if (part.contentType === "text/html" && !htmlBody) {
          htmlBody = decoded;
        } else if (part.isAttachment && part.filename) {
          // Save attachments (certificate images/PDFs)
          attachments.push({
            filename: part.filename,
            content_type: part.contentType,
            content: decoded, // base64-encoded
            size: part.size || 0,
          });
          console.log(`  📎 Attachment: ${part.filename} (${part.contentType}, ${part.size || '?'} bytes)`);
        }
      }

      // Fallback: if no structured parts found, use raw body
      if (!textBody && !htmlBody) {
        textBody = decodeQuotedPrintable(rawEmail);
      }
    } catch (e) {
      console.error("Failed to parse email body:", e);
      textBody = "";
    }

    console.log(`Email parsed: ${from} → ${to} | Subject: ${subject} | Attachments: ${attachments.length}`);

    const payload = {
      from: from,
      to: to,
      subject: subject,
      text: textBody,
      html: htmlBody,
      attachments: attachments,
      "message-id": messageId,
    };

    const webhookUrl = env.BREATHE_WEBHOOK_URL || "https://breathe.sublettlabs.com/api/email/ceu-webhook";

    try {
      const response = await fetch(webhookUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Email-Source": "cloudflare-email-worker",
        },
        body: JSON.stringify(payload),
      });

      const result = await response.json();

      console.log(`Email forwarded: ${from} → ${to} | Subject: ${subject}`);
      console.log(`Webhook response: ${response.status}`, JSON.stringify(result));

      if (result.success) {
        console.log(`✅ CEU imported: ${result.title} (${result.credits} credits) | Cert: ${result.certificate_path || 'none'}`);
      } else {
        console.log(`⚠️ Webhook returned: ${result.message}`);
      }
    } catch (error) {
      console.error("Failed to POST to Breathe webhook:", error);
    }
  },
};

/**
 * Parse MIME parts from raw email
 */
function parseMimeParts(raw) {
  const parts = [];

  // Find boundary
  const boundaryMatch = raw.match(/boundary="?([a-zA-Z0-9'()+,_\-.\/:=?]+)"?/i);
  if (!boundaryMatch) {
    // No multipart — try to find single part
    const headerEnd = raw.indexOf("\r\n\r\n") >= 0 ? raw.indexOf("\r\n\r\n") : raw.indexOf("\n\n");
    if (headerEnd >= 0) {
      const headers = raw.substring(0, headerEnd);
      const body = raw.substring(headerEnd + 4);
      const ctMatch = headers.match(/Content-Type:\s*([^\r\n;]+)/i);
      const cteMatch = headers.match(/Content-Transfer-Encoding:\s*([^\r\n]+)/i);
      const cdMatch = headers.match(/Content-Disposition:\s*([^\r\n]+)/i);
      const fnameMatch = headers.match(/filename="?([^";\r\n]+)"?/i);
      parts.push({
        contentType: ctMatch ? ctMatch[1].trim().toLowerCase() : "text/plain",
        encoding: cteMatch ? cteMatch[1].trim().toLowerCase() : "7bit",
        disposition: cdMatch ? cdMatch[1].trim().toLowerCase() : "",
        filename: fnameMatch ? fnameMatch[1].trim() : null,
        isAttachment: false,
        body: body,
      });
    }
    return parts;
  }

  const boundary = "--" + boundaryMatch[1];
  const sections = raw.split(boundary);

  for (const section of sections) {
    if (!section.trim() || section.trim() === "--") continue;

    const headerEnd = section.indexOf("\r\n\r\n") >= 0
      ? section.indexOf("\r\n\r\n")
      : section.indexOf("\n\n");
    if (headerEnd < 0) continue;

    const headers = section.substring(0, headerEnd);
    const body = section.substring(headerEnd + 4).trim();

    const ctMatch = headers.match(/Content-Type:\s*([^\r\n;]+)/i);
    const cteMatch = headers.match(/Content-Transfer-Encoding:\s*([^\r\n]+)/i);
    const cdMatch = headers.match(/Content-Disposition:\s*([^\r\n]+)/i);
    const fnameMatch = headers.match(/filename="?([^";\r\n]+)"?/i);
    const cidMatch = headers.match(/Content-ID:\s*<([^>]+)>/i);

    const contentType = ctMatch ? ctMatch[1].trim().toLowerCase() : "text/plain";
    const encoding = cteMatch ? cteMatch[1].trim().toLowerCase() : "7bit";
    const disposition = cdMatch ? cdMatch[1].trim().toLowerCase() : "";
    const filename = fnameMatch ? fnameMatch[1].trim() : null;
    const contentId = cidMatch ? cidMatch[1].trim() : null;

    // Determine if this is an attachment
    const isAttachment = (
      (disposition && disposition.includes("attachment")) ||
      (filename && (contentType.startsWith("image/") || contentType.includes("pdf"))) ||
      (disposition && disposition.includes("inline") && filename)
    );

    // Skip non-text parts unless they're attachments
    if (!contentType.startsWith("text/") && !isAttachment) {
      continue;
    }

    // For attachments, keep the raw encoded body (will be decoded later)
    if (isAttachment) {
      parts.push({
        contentType,
        encoding,
        disposition,
        filename: filename || `attachment.${contentType.split("/")[1] || "bin"}`,
        isAttachment: true,
        contentId,
        body,
        size: body.length,
      });
    } else if (contentType.startsWith("text/")) {
      parts.push({ contentType, encoding, disposition, filename: null, isAttachment: false, body });
    }
  }

  return parts;
}

/**
 * Decode a MIME part based on its encoding
 */
function decodePart(part) {
  let body = part.body;

  if (part.isAttachment) {
    // For attachments, keep base64-encoded content for the API
    if (part.encoding === "base64") {
      // Clean up whitespace in base64
      return body.replace(/\s/g, "");
    }
    // For other encodings, try to base64-encode the raw content
    try {
      return btoa(body);
    } catch (e) {
      console.error("Failed to encode attachment:", e);
      return "";
    }
  }

  switch (part.encoding) {
    case "quoted-printable":
      body = decodeQuotedPrintable(body);
      break;
    case "base64":
      try {
        body = atob(body.replace(/\s/g, ""));
      } catch (e) {
        console.error("Base64 decode failed:", e);
      }
      break;
    case "7bit":
    case "8bit":
    case "binary":
    default:
      break;
  }

  return body;
}

/**
 * Decode quoted-printable encoding
 */
function decodeQuotedPrintable(text) {
  return text
    .replace(/=\r?\n/g, "")
    .replace(/=([0-9A-Fa-f]{2})/g, (_, hex) => {
      return String.fromCharCode(parseInt(hex, 16));
    })
    .replace(/^>{1,}/gm, "")
    .replace(/\r\n/g, "\n")
    .trim();
}