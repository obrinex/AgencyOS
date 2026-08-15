/**
 * The written parts of the members' portal: house rules and the FAQ.
 *
 * Plain data, not a CMS. Two pages that change a few times a year do not
 * justify a database, an editor and a permissions model — and a file in the
 * repo has version history, review and a rollback for free.
 *
 * Edit here, commit, and it ships with the next deploy.
 */

export const GUIDELINES = [
  {
    title: "What leaves the room",
    body:
      "Nothing, unless the person who said it says otherwise. Numbers, deals, " +
      "problems and half-formed ideas are all shared here on the understanding " +
      "that they stay here. If you want to repeat something outside, ask first — " +
      "it is a short message and it costs nothing.",
  },
  {
    title: "Say the real number",
    body:
      "The circle is only worth the honesty in it. A room where everyone reports " +
      "the flattering version is a networking event, and you already have enough " +
      "of those. If you are down a quarter, say so — that is the conversation " +
      "worth having.",
  },
  {
    title: "Answer when you can help",
    body:
      "You were admitted partly because of what you would be able to give someone " +
      "else. Nobody is counting, but a member who only ever asks is noticed as " +
      "surely as one who only ever answers.",
  },
  {
    title: "No selling to each other",
    body:
      "Introductions, referrals and 'I know someone' are the point. Pitching your " +
      "product to the room is not. If a conversation turns into business, take it " +
      "to a direct message and settle it between yourselves.",
  },
  {
    title: "Refer people you would vouch for",
    body:
      "Your invitations carry your name on them. A referral is read sooner, not " +
      "accepted sooner — everyone answers the same eleven questions and is scored " +
      "the same way. Sending someone who wastes that read costs you more than it " +
      "costs them.",
  },
  {
    title: "Seats are per quarter, and they are real",
    body:
      "Ten people join each intake. If the room stops being useful, we shrink it " +
      "rather than fill it. Membership is not a subscription you can renew by " +
      "paying attention to nothing.",
  },
];

export const FAQ = [
  {
    q: "Who else can see my contact details?",
    a:
      "Only what you switch on. Your name, company and projects are visible to " +
      "other members; your email, phone and each social are hidden until you turn " +
      "them on individually in Profile. You gave those to us to be assessed, so " +
      "nothing is published on your behalf.",
  },
  {
    q: "Can I be in the circle without being in the directory?",
    a:
      "Yes. Turn off 'List me in the directory' in Profile and other members see " +
      "your name and nothing else. You keep the room, the projects page and the " +
      "assistant.",
  },
  {
    q: "How many people can I refer?",
    a:
      "Twenty-five invitations over your membership, which is far more than anyone " +
      "sensible uses. Each link works once. You can withdraw one that has not been " +
      "used yet.",
  },
  {
    q: "Does a referral get someone in?",
    a:
      "No — it gets them read. They answer the same eleven questions and are scored " +
      "the same way, and you will see whether it went anywhere. If referrals bought " +
      "seats, the circle would be a place you get into by knowing someone.",
  },
  {
    q: "What is the assistant allowed to see?",
    a:
      "Your own thread and nothing else. It cannot read the agency's client data, " +
      "other members' messages, or anyone else's application.",
  },
  {
    q: "Who reads the community room?",
    a:
      "Members and the Obrinex team. The team is in it because this is our room " +
      "too — a host who cannot see their own community is not hosting it. Nobody " +
      "else, including clients, can reach it.",
  },
  {
    q: "What happens to my projects if I leave?",
    a:
      "Your profile and projects come out of the directory with you. Messages you " +
      "posted in the community stay, because a thread with holes in it is not a " +
      "record of a conversation.",
  },
  {
    q: "Something here is wrong or missing.",
    a:
      "Say so in the community room, or ask the assistant to flag it. This portal " +
      "is early and the fastest way to change it is to tell us.",
  },
];
