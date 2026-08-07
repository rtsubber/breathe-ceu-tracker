/**
 * Cloudflare Email Worker — Breathe CEU Email Forwarding
 *
 * Receives emails at *@breathe.sublettlabs.com via Cloudflare Email Routing,
 * parses them, and POSTs to the Breathe API webhook for auto-CEU logging.
 *
 * Deploy: wrangler deploy
 * Cloudflare Dashboard → Email Routing → Route to this Worker
 */

export default {
  async email(message, env, ctx) {
    // Build the webhook payload from the incoming email
    const from = message.headers.get("from") || message.from || "";
    const to = message.headers.get("to") || message.to || "";
    const subject = message.headers.get("subject") || "";
    const messageId = message.headers.get("message-id") || "";

    // Read the email body
    let textBody = "";
    let htmlBody = "";

    try {
      const rawEmail = await new Response(message.raw).text();
      // Split into text and html parts (basic parsing)
      const textMatch = rawEmail.match(/Content-Type:\s*text\/plain[\s\S]*?\r?\n\r?\n([\s\S]*?)(?=\r?\n--|\r?\nContent-Type:|$)/i);
      const htmlMatch = rawEmail.match(/Content-Type:\s*text\/html[\s\S]*?\r?\n\r?\n([\s\S]*?)(?=\r?\n--|\r?\nContent-Type:|$)/i);
      if (textMatch) textBody = textMatch[1].trim();
      if (htmlMatch) htmlBody = htmlMatch[1].trim();
      // If no parts found, use raw body
      if (!textBody && !htmlBody) textBody = rawEmail;
    } catch (e) {
      console.error("Failed to parse email body:", e);
      textBody = "";
    }

    // Collect attachments
    const attachments = [];
    // Note: Cloudflare Email Workers don't expose attachments directly in the message object.
    // For attachment support, we'd need to parse the raw MIME. Basic version: text/html only.

    // Build payload for Breathe webhook
    const payload = {
      from: from,
      to: to,
      subject: subject,
      text: textBody,
      html: htmlBody,
      attachments: attachments,
      "message-id": messageId,
    };

    // POST to Breathe API webhook
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

      // Optionally send a reply email confirming receipt
      if (result.success) {
        console.log(`✅ CEU imported: ${result.title} (${result.credits} credits)`);
      } else {
        console.log(`⚠️ Webhook returned: ${result.message}`);
      }
    } catch (error) {
      console.error("Failed to POST to Breathe webhook:", error);
    }
  },
};