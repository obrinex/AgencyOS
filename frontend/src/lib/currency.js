export const CURRENCY_SYMBOLS = { INR: "\u20B9", USD: "$" };
export const SUPPORTED_CURRENCIES = ["INR", "USD"];
export const BASE_CURRENCY = "INR";

export function formatMoney(amount, currencyCode = BASE_CURRENCY) {
  const symbol = CURRENCY_SYMBOLS[currencyCode] || `${currencyCode} `;
  return `${symbol}${(amount || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export const EXPENSE_TYPES = [
  { value: "personal_withdrawal", label: "Personal Withdrawal" },
  { value: "business_expense", label: "Business Expense" },
  { value: "unclassified", label: "Unclassified" },
];
