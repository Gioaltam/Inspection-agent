const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD"
});

const PRODUCTS = {
  single_family: {
    label: "Single-Family Home",
    price: 150
  },
  large_or_multi: {
    label: "Larger / Multi-unit",
    price: 250
  }
};

function getTodayString() {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDateDisplay(value) {
  if (!value) return "Select a date";
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(year, month - 1, day);
  if (Number.isNaN(parsed.getTime())) return "Select a valid date";
  return parsed.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric"
  });
}

function formatTimeDisplay(value) {
  if (!value) return "Select a time";
  const [hours, minutes] = value.split(":").map(Number);
  const date = new Date();
  date.setHours(hours, minutes, 0, 0);
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function generateConfirmationId() {
  return Math.random().toString(36).slice(2, 10).toUpperCase();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("billingForm");
  if (!form) return;

  const formContainer = document.getElementById("formContainer");
  const messageEl = document.getElementById("formMessages");
  const priceBadge = document.getElementById("priceBadge");
  const priceAmountEl = priceBadge.querySelector("span:last-child");
  const summaryProperty = document.getElementById("summaryProperty");
  const summaryDate = document.getElementById("summaryDate");
  const summaryTime = document.getElementById("summaryTime");
  const summaryAddress = document.getElementById("summaryAddress");
  const summaryContact = document.getElementById("summaryContact");

  const propertyTypeInputs = Array.from(form.querySelectorAll("input[name='property_type']"));
  const streetInput = document.getElementById("street");
  const cityInput = document.getElementById("city");
  const stateInput = document.getElementById("state");
  const zipInput = document.getElementById("zip");
  const dateInput = document.getElementById("preferredDate");
  const timeInput = document.getElementById("preferredTime");
  const nameInput = document.getElementById("fullName");
  const emailInput = document.getElementById("email");
  const phoneInput = document.getElementById("phone");
  const submitButton = document.getElementById("payScheduleButton");
  const buttonText = submitButton.querySelector(".button-text");

  const todayStr = getTodayString();
  dateInput.min = todayStr;
  if (!dateInput.value) {
    dateInput.value = todayStr;
  }

  function getSelectedProductKey() {
    const selected = propertyTypeInputs.find((input) => input.checked);
    return selected ? selected.value : propertyTypeInputs[0]?.value;
  }

  function updatePriceDisplay() {
    const key = getSelectedProductKey();
    const product = key ? PRODUCTS[key] : null;
    if (!product) return;
    priceAmountEl.textContent = currencyFormatter.format(product.price);
    summaryProperty.textContent = `${product.label} - ${currencyFormatter.format(product.price)}`;
  }

  function buildAddressText() {
    const street = streetInput.value.trim();
    const city = cityInput.value.trim();
    const state = stateInput.value.trim().toUpperCase();
    const zip = zipInput.value.trim();

    if (stateInput.value !== state) {
      stateInput.value = state;
    }

    const segments = [];
    if (street) segments.push(street);
    const cityState = [city, state].filter(Boolean).join(", ");
    if (cityState) segments.push(cityState);
    if (zip) segments.push(zip);

    return segments.length ? segments.join(" | ") : "Enter address details";
  }

  function updateAddressSummary() {
    summaryAddress.textContent = buildAddressText();
  }

  function updateDateSummary() {
    summaryDate.textContent = formatDateDisplay(dateInput.value);
  }

  function updateTimeSummary() {
    summaryTime.textContent = formatTimeDisplay(timeInput.value);
  }

  function updateContactSummary() {
    const name = nameInput.value.trim();
    const email = emailInput.value.trim();
    const parts = [];
    if (name) parts.push(name);
    if (email) parts.push(email.toLowerCase());
    summaryContact.textContent = parts.length ? parts.join(" | ") : "Add name & email";
  }

  propertyTypeInputs.forEach((input) => {
    input.addEventListener("change", updatePriceDisplay);
  });

  [streetInput, cityInput, stateInput, zipInput].forEach((input) => {
    input.addEventListener("input", updateAddressSummary);
  });

  dateInput.addEventListener("change", updateDateSummary);
  timeInput.addEventListener("change", updateTimeSummary);
  nameInput.addEventListener("input", updateContactSummary);
  emailInput.addEventListener("input", updateContactSummary);

  updatePriceDisplay();
  updateAddressSummary();
  updateDateSummary();
  updateTimeSummary();
  updateContactSummary();

  function validateForm() {
    const errors = [];
    const selectedKey = getSelectedProductKey();
    if (!selectedKey) {
      errors.push("Please select a property type.");
    }

    if (!streetInput.value.trim()) errors.push("Street address is required.");
    if (!cityInput.value.trim()) errors.push("City is required.");
    if (!stateInput.value.trim()) errors.push("State is required.");
    if (!zipInput.value.trim()) errors.push("ZIP code is required.");

    if (!dateInput.value) {
      errors.push("Preferred date is required.");
    } else {
      const [year, month, day] = dateInput.value.split("-").map(Number);
      const selectedDate = new Date(year, month - 1, day);
      selectedDate.setHours(0, 0, 0, 0);
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      if (selectedDate < today) {
        errors.push("Preferred date must be today or later.");
      }
    }

    if (!timeInput.value) errors.push("Preferred time is required.");
    if (!nameInput.value.trim()) errors.push("Contact name is required.");

    const emailValue = emailInput.value.trim();
    if (!emailValue) {
      errors.push("Email is required.");
    } else if (!/.+@.+\..+/.test(emailValue)) {
      errors.push("Enter a valid email address.");
    }

    if (!phoneInput.value.trim()) errors.push("Phone number is required.");

    if (errors.length) {
      messageEl.innerHTML = errors.map((err) => `<div>${err}</div>`).join("");
      messageEl.classList.add("active");
      return false;
    }

    messageEl.classList.remove("active");
    messageEl.textContent = "";
    return true;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!validateForm()) {
      return;
    }

    const productKey = getSelectedProductKey();
    const product = PRODUCTS[productKey];
    const addressText = buildAddressText();
    const summaryData = {
      type: product.label,
      price: currencyFormatter.format(product.price),
      date: formatDateDisplay(dateInput.value),
      time: formatTimeDisplay(timeInput.value),
      address: addressText,
      contactName: nameInput.value.trim(),
      contactEmail: emailInput.value.trim().toLowerCase(),
      contactPhone: phoneInput.value.trim()
    };

    submitButton.disabled = true;
    submitButton.classList.add("loading");
    buttonText.textContent = "Processing...";

    Array.from(form.elements).forEach((el) => {
      el.disabled = true;
    });

    setTimeout(() => {
      const confirmationId = generateConfirmationId();
      const safeAddress = escapeHtml(summaryData.address).replace(/ \| /g, "<br>");
      const contactLine = `${summaryData.contactName} | ${summaryData.contactEmail}`;
      const safeContact = escapeHtml(contactLine);
      const phoneLine = summaryData.contactPhone ? `<div class="value-secondary">Phone: ${escapeHtml(summaryData.contactPhone)}</div>` : "";

      formContainer.innerHTML = `
        <div class="confirmation">
          <div class="confirmation-icon">&#10003;</div>
          <h2>Inspection Scheduled</h2>
          <p style="margin-top: 0.6rem; color: rgba(255, 255, 255, 0.7);">Thank you! Your inspection is confirmed and a confirmation email is on the way.</p>
          <div class="confirmation-details">
            <div class="detail">
              <div class="label">Confirmation ID</div>
              <div class="value">${escapeHtml(confirmationId)}</div>
            </div>
            <div class="detail">
              <div class="label">Service</div>
              <div class="value">${escapeHtml(summaryData.type)} - ${escapeHtml(summaryData.price)}</div>
            </div>
            <div class="detail">
              <div class="label">Date &amp; Time</div>
              <div class="value">${escapeHtml(summaryData.date)} at ${escapeHtml(summaryData.time)}</div>
            </div>
            <div class="detail">
              <div class="label">Address</div>
              <div class="value">${safeAddress}</div>
            </div>
            <div class="detail">
              <div class="label">Contact</div>
              <div class="value">${safeContact}</div>
              ${phoneLine}
            </div>
          </div>
          <a class="btn btn-primary" href="landing.html">Back to Home</a>
        </div>
      `;
    }, 1200);
  });
});
