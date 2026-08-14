/**
 * eMaktab — Secure Gemini AI Proxy
 * ----------------------------------------------------------
 * This Cloud Function keeps your Gemini API key on the server.
 * The browser NEVER sees the key — it only talks to this function.
 *
 * Deploy with:
 *   firebase deploy --only functions
 *
 * Set your key (ONE TIME, server-side only) with:
 *   firebase functions:secrets:set GEMINI_API_KEY
 * (it will prompt you to paste the key — it is stored securely,
 *  not in your code, not in git, not visible to users)
 */

const { onRequest } = require("firebase-functions/v2/https");
const { defineSecret } = require("firebase-functions/params");
const { GoogleGenAI } = require("@google/genai");

const GEMINI_API_KEY = defineSecret("GEMINI_API_KEY");
const ZOOM_ACCOUNT_ID = defineSecret("ZOOM_ACCOUNT_ID");
const ZOOM_CLIENT_ID = defineSecret("ZOOM_CLIENT_ID");
const ZOOM_CLIENT_SECRET = defineSecret("ZOOM_CLIENT_SECRET");
const ZOOM_USER_EMAIL = defineSecret("ZOOM_USER_EMAIL");

exports.geminiProxy = onRequest(
  {
    secrets: [GEMINI_API_KEY],
    cors: true, // allow browser requests from your site
    region: "us-central1",
    invoker: "public", // allow public/unauthenticated access from the browser
    timeoutSeconds: 60,
  },
  async (req, res) => {
    // Only allow POST
    if (req.method !== "POST") {
      res.status(405).json({ error: "Method not allowed" });
      return;
    }

    try {
      const { prompt, system, history } = req.body || {};

      let contents;
      if (Array.isArray(history) && history.length) {
        contents = history;
      } else if (prompt && typeof prompt === "string") {
        contents = [{ role: "user", parts: [{ text: prompt }] }];
      } else {
        res.status(400).json({ error: "Missing 'prompt' or 'history' field" });
        return;
      }

      const key = GEMINI_API_KEY.value();
      const ai = new GoogleGenAI({ apiKey: key });

      // Lower token cap = faster generation (Gemini streams tokens sequentially,
      // so a shorter cap finishes sooner). 700 is still enough for a full
      // step-by-step tutoring answer in Tajik.
      const config = { maxOutputTokens: 700, temperature: 0.7 };
      if (system) {
        config.systemInstruction = system;
      }

      // Retry transient "model overloaded" errors a few times before giving up,
      // so students don't see an error for something that resolves in a second.
      const MAX_RETRIES = 3;
      let lastErr;
      for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
        try {
          const response = await ai.models.generateContent({
            model: "gemini-2.5-flash-lite",
            contents,
            config,
          });
          const text = response?.text || "";
          res.status(200).json({ text });
          return;
        } catch (err) {
          lastErr = err;
          const msg = (err?.message || "").toLowerCase();
          const isTransient =
            msg.includes("503") ||
            msg.includes("overloaded") ||
            msg.includes("unavailable") ||
            msg.includes("429") ||
            msg.includes("rate");
          if (!isTransient || attempt === MAX_RETRIES) break;
          // Exponential backoff: 500ms, 1000ms, 2000ms
          await new Promise((r) => setTimeout(r, 500 * Math.pow(2, attempt)));
        }
      }

      throw lastErr;
    } catch (err) {
      console.error("geminiProxy error:", err);
      const msg = (err?.message || "").toLowerCase();
      const isTransient =
        msg.includes("503") || msg.includes("overloaded") || msg.includes("unavailable");
      res
        .status(isTransient ? 503 : 500)
        .json({ error: err?.message || "Internal server error" });
    }
  }
);

/**
 * eMaktab — Zoom Meeting Creator
 * ----------------------------------------------------------
 * Creates a real Zoom meeting via a Server-to-Server OAuth app when a
 * student books a mentor session. The Zoom Client Secret never touches
 * the browser — only this function talks to Zoom's API.
 *
 * Set secrets (ONE TIME) with:
 *   firebase functions:secrets:set ZOOM_ACCOUNT_ID
 *   firebase functions:secrets:set ZOOM_CLIENT_ID
 *   firebase functions:secrets:set ZOOM_CLIENT_SECRET
 *   firebase functions:secrets:set ZOOM_USER_EMAIL
 */
exports.createZoomMeeting = onRequest(
  {
    secrets: [ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET, ZOOM_USER_EMAIL],
    cors: true,
    region: "us-central1",
    invoker: "public",
    timeoutSeconds: 30,
  },
  async (req, res) => {
    if (req.method !== "POST") {
      res.status(405).json({ error: "Method not allowed" });
      return;
    }

    try {
      const { topic, startTimeISO, durationMinutes } = req.body || {};
      if (!topic || !startTimeISO) {
        res.status(400).json({ error: "Missing 'topic' or 'startTimeISO' field" });
        return;
      }

      const accountId = ZOOM_ACCOUNT_ID.value();
      const clientId = ZOOM_CLIENT_ID.value();
      const clientSecret = ZOOM_CLIENT_SECRET.value();
      const userEmail = ZOOM_USER_EMAIL.value();

      // 1) Get an OAuth access token (Server-to-Server)
      const basicAuth = Buffer.from(`${clientId}:${clientSecret}`).toString("base64");
      const tokenResp = await fetch(
        `https://zoom.us/oauth/token?grant_type=account_credentials&account_id=${accountId}`,
        {
          method: "POST",
          headers: { Authorization: `Basic ${basicAuth}` },
        }
      );
      const tokenData = await tokenResp.json();
      if (!tokenResp.ok || !tokenData.access_token) {
        console.error("Zoom OAuth error:", tokenData);
        res.status(502).json({ error: "Zoom auth failed", details: tokenData });
        return;
      }

      // 2) Create the meeting
      const meetingResp = await fetch(
        `https://api.zoom.us/v2/users/${encodeURIComponent(userEmail)}/meetings`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${tokenData.access_token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            topic: String(topic).slice(0, 200),
            type: 2, // scheduled meeting
            start_time: startTimeISO,
            duration: durationMinutes || 30,
            timezone: "Asia/Dushanbe",
            settings: {
              join_before_host: true,
              waiting_room: false,
              approval_type: 2,
            },
          }),
        }
      );
      const meetingData = await meetingResp.json();
      if (!meetingResp.ok) {
        console.error("Zoom create meeting error:", meetingData);
        res.status(502).json({ error: "Zoom meeting creation failed", details: meetingData });
        return;
      }

      res.status(200).json({
        join_url: meetingData.join_url,
        start_url: meetingData.start_url,
        meeting_id: meetingData.id,
        password: meetingData.password || "",
      });
    } catch (err) {
      console.error("createZoomMeeting error:", err);
      res.status(500).json({ error: err?.message || "Internal server error" });
    }
  }
);