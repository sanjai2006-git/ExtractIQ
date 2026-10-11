
const API_BASE = "";

let reviewQueue = [];
let invoiceHistory = [];
let activeExtraction = null;

const $ = (selector) => document.querySelector(selector);

// -------------------- API HELPERS --------------------

async function apiRequest(url, options = {}) {
    const response = await fetch(`${API_BASE}${url}`, options);

    if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Request failed (${response.status})`);
    }

    if (response.status === 204) return null;

    const contentType = response.headers.get("content-type") || "";

    return contentType.includes("application/json")
        ? response.json()
        : response.text();
}

function getList(result, keys = []) {
    if (Array.isArray(result)) return result;

    for (const key of keys) {
        if (Array.isArray(result?.[key])) return result[key];
    }

    return [];
}

function escapeHTML(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function formatDate(value) {
    if (!value) return "—";

    const date = new Date(value);

    return Number.isNaN(date.getTime())
        ? String(value)
        : date.toLocaleString();
}

function getDocumentId(item) {
    return (
        item?.document_id ??
        item?.document?.id ??
        item?.documentId ??
        item?.id ??
        null
    );
}

function getExtraction(item) {
    // DocumentDetailOut contains item.extraction.
    // ExtractionOut itself contains data and id.
    return item?.extraction ?? item?.extraction_record ?? (
        item?.document_id != null && item?.data != null
            ? item
            : null
    );
}

function getExtractionId(item) {
    const extraction = getExtraction(item);

    return (
        item?.extraction_id ??
        extraction?.id ??
        null
    );
}

function getInvoiceData(item) {
    const extraction = getExtraction(item);

    return (
        extraction?.corrected_data ??
        extraction?.data ??
        item?.extracted_data ??
        item?.fields ??
        {}
    );
}

function getConfidence(item) {
    const extraction = getExtraction(item);

    const raw =
        extraction?.overall_confidence ??
        item?.overall_confidence ??
        item?.confidence ??
        item?.extraction?.confidence;

    if (raw === null || raw === undefined || raw === "") {
        return "—";
    }

    const value = Number(raw);

    if (!Number.isFinite(value)) return "—";

    return `${Math.round(value <= 1 ? value * 100 : value)}%`;
}

function getStatus(item) {
    const extraction = getExtraction(item);

    const raw = String(
        extraction?.status ??
        item?.status ??
        item?.document_status ??
        ""
    ).toLowerCase();

    if (raw.includes("reject")) return "Rejected";

    if (
        raw.includes("approved") ||
        raw === "accepted"
    ) return "Accepted";

    if (
        raw.includes("pending") ||
        raw.includes("review")
    ) return "Pending";

    if (raw.includes("fail") || raw.includes("error")) {
        return "Failed";
    }

    if (raw.includes("correct")) return "Corrected";

    if (
        raw.includes("extract") ||
        raw.includes("complete") ||
        raw.includes("process")
    ) return "Extracted";

    if (extraction?.data || item?.extracted_data) {
        return "Extracted";
    }

    return "Uploaded";
}

function showMessage(selector, message, isError = false) {
    const element = $(selector);
    if (!element) return;

    element.textContent = message;
    element.style.color = isError ? "#dc2626" : "";
}

// -------------------- DASHBOARD --------------------

function updateDashboardCounts() {
    $("#total-invoices") &&
        ($("#total-invoices").textContent = invoiceHistory.length);

    $("#extracted-invoices") &&
        ($("#extracted-invoices").textContent =
            invoiceHistory.filter((item) =>
                ["Extracted", "Accepted", "Corrected"].includes(
                    getStatus(item)
                )
            ).length);

    $("#pending-invoices") &&
        ($("#pending-invoices").textContent =
            invoiceHistory.filter(
                (item) => getStatus(item) === "Pending"
            ).length);

    $("#rejected-invoices") &&
        ($("#rejected-invoices").textContent =
            invoiceHistory.filter(
                (item) => getStatus(item) === "Rejected"
            ).length);

    $("#queue-count") &&
        ($("#queue-count").textContent = reviewQueue.length);
}

async function loadDashboard() {
    await Promise.allSettled([
        loadInvoiceHistory(),
        loadReviewQueue()
    ]);

    updateDashboardCounts();
}

// -------------------- REVIEW QUEUE --------------------

async function loadReviewQueue() {
    const list = $("#queue-list");

    try {
        const result = await apiRequest("/review/queue");

        reviewQueue = getList(result, [
            "items", "queue", "results"
        ]);

        renderQueue();
    } catch (error) {
        console.error("Review queue error:", error);

        if (list) {
            list.innerHTML = `
                <p class="error-message">
                    Could not load the review queue.
                </p>
            `;
        }
    }
}

function renderQueue() {
    const list = $("#queue-list");
    if (!list) return;

    if (!reviewQueue.length) {
        list.innerHTML = `
            <p class="empty-message">
                No documents waiting for review.
            </p>
        `;
        return;
    }

    list.innerHTML = reviewQueue.map((item, index) => {
        const filename =
            item?.filename ??
            item?.document?.filename ??
            `Invoice ${index + 1}`;

        return `
            <button
                class="queue-item"
                type="button"
                data-extraction-id="${escapeHTML(getExtractionId(item) ?? "")}"
                data-document-id="${escapeHTML(getDocumentId(item) ?? "")}"
            >
                <span class="queue-item-title">
                    ${escapeHTML(filename)}
                </span>
                <span class="queue-item-meta">
                    Confidence: ${escapeHTML(getConfidence(item))}
                </span>
            </button>
        `;
    }).join("");

    list.querySelectorAll(".queue-item").forEach((button) => {
        button.addEventListener("click", () => {
            const extractionId = button.dataset.extractionId;
            const documentId = button.dataset.documentId;

            selectExtraction({
                extractionId,
                documentId
            });
        });
    });
}

// -------------------- INVOICE HISTORY --------------------

async function loadInvoiceHistory() {
    const body = $("#invoice-history-body");

    if (body) {
        body.innerHTML = `
            <tr><td colspan="6">Loading invoice history...</td></tr>
        `;
    }

    try {
        const result = await apiRequest("/documents");

        const documents = getList(result, [
            "documents", "items", "results"
        ]);

        // GET /documents returns DocumentOut, which does not include
        // extraction.data. Fetch each detail to populate invoice fields.
        invoiceHistory = await Promise.all(
            documents.map(async (document) => {
                try {
                    return await apiRequest(
                        `/documents/${encodeURIComponent(document.id)}`
                    );
                } catch (error) {
                    console.warn(
                        `Could not load document ${document.id} details:`,
                        error
                    );
                    return document;
                }
            })
        );

        renderInvoiceHistory();
    } catch (error) {
        console.error("Invoice history error:", error);

        if (body) {
            body.innerHTML = `
                <tr>
                    <td colspan="6">
                        Could not load invoice history.
                        Check the backend and try Refresh.
                    </td>
                </tr>
            `;
        }
    }
}

function renderInvoiceHistory() {
    const body = $("#invoice-history-body");
    if (!body) return;

    const searchText = ($("#invoice-search")?.value ?? "")
        .trim()
        .toLowerCase();

    const filtered = invoiceHistory.filter((item) => {
        const data = getInvoiceData(item);

        const searchable = [
            item?.filename,
            data?.invoice_number,
            data?.vendor_name
        ].filter(Boolean).join(" ");

        return searchable.toLowerCase().includes(searchText);
    });

    if (!filtered.length) {
        body.innerHTML = `
            <tr><td colspan="6">No invoices found.</td></tr>
        `;
        return;
    }

    body.innerHTML = filtered.map((item, index) => {
        const documentId = getDocumentId(item);
        const data = getInvoiceData(item);

        const filename =
            item?.filename ??
            item?.document?.filename ??
            `Invoice ${index + 1}`;

        return `
            <tr>
                <td>${escapeHTML(filename)}</td>
                <td>${escapeHTML(data?.invoice_number ?? "—")}</td>
                <td>${escapeHTML(data?.vendor_name ?? "—")}</td>
                <td>${escapeHTML(getConfidence(item))}</td>
                <td>${escapeHTML(getStatus(item))}</td>
                <td>
                    <button
                        type="button"
                        class="view-invoice-btn"
                        data-document-id="${escapeHTML(documentId ?? "")}"
                    >View</button>
                </td>
            </tr>
        `;
    }).join("");

    body.querySelectorAll(".view-invoice-btn").forEach((button) => {
        button.addEventListener("click", () => {
            const documentId = button.dataset.documentId;

            if (documentId) {
                selectExtraction({ documentId });
            }
        });
    });
}

// -------------------- OPEN INVOICE --------------------

async function selectExtraction({ documentId, extractionId } = {}) {
    const section = $("#document-review");
    if (!section) return;

    section.innerHTML = "<p>Loading invoice details...</p>";

    try {
        let item = null;

        // A queue entry uses an extraction ID; a history entry uses
        // a document ID. Do not confuse the two.
        if (documentId) {
            item = await apiRequest(
                `/documents/${encodeURIComponent(documentId)}`
            );
        } else if (extractionId) {
            item = reviewQueue.find(
                (entry) =>
                    String(getExtractionId(entry)) === String(extractionId)
            );

            if (item?.document_id != null) {
                item = await apiRequest(
                    `/documents/${encodeURIComponent(item.document_id)}`
                );
            }
        }

        if (!item) {
            throw new Error("The requested document could not be found.");
        }

        activeExtraction = item;
        renderDetail(item);
    } catch (error) {
        console.error("Invoice details error:", error);

        section.innerHTML = `
            <div class="main-empty">
                <h2>Unable to open invoice</h2>
                <p>${escapeHTML(error.message)}</p>
                <button id="retry-dashboard" type="button">Back to Dashboard</button>
            </div>
        `;

        $("#retry-dashboard")?.addEventListener("click", showDashboard);
    }
}

// -------------------- REVIEW DETAILS --------------------

function showDashboard() {
    activeExtraction = null;

    const section = $("#document-review");

    if (section) {
        section.innerHTML = `
            <div class="main-empty">
                <h2>Select an invoice to review</h2>
                <p>
                    Choose an invoice from the history table
                    or review queue.
                </p>
            </div>
        `;
    }

    loadDashboard();
}

function renderDetail(item) {
    const section = $("#document-review");
    if (!section) return;

    const documentId = getDocumentId(item);
    const extraction = getExtraction(item);
    const fields = getInvoiceData(item);

    const filename =
        item?.filename ??
        item?.document?.filename ??
        "Invoice";

    const entries = Object.entries(fields || {});

    const fileUrl = documentId
        ? `/documents/${encodeURIComponent(documentId)}/file`
        : "";

    section.innerHTML = `
        <div class="review-header">
            <div>
                <h2>${escapeHTML(filename)}</h2>
                <p>Confidence: ${escapeHTML(getConfidence(item))}</p>
            </div>
            <button id="back-dashboard" type="button">
                Back to Dashboard
            </button>
        </div>

        <div class="review-layout">
            <div class="pdf-preview">
                ${
                    fileUrl
                        ? `<iframe title="Invoice PDF"
                             src="${escapeHTML(fileUrl)}"></iframe>`
                        : "<p>PDF preview unavailable.</p>"
                }
            </div>

            <div class="extraction-panel">
                <h3>Extracted Fields</h3>

                ${
                    entries.length
                        ? `<div class="extracted-fields">
                            ${entries.map(([key, value]) => {
                                const displayValue =
                                    value !== null && typeof value === "object"
                                        ? JSON.stringify(value, null, 2)
                                        : value ?? "";

                                return `
                                    <label class="field-row">
                                        <span>${escapeHTML(key)}</span>
                                        <textarea
                                            class="extracted-field-input"
                                            data-field="${escapeHTML(key)}"
                                            rows="${typeof value === "object" && value !== null ? 4 : 1}"
                                        >${escapeHTML(displayValue)}</textarea>
                                    </label>
                                `;
                            }).join("")}
                        </div>`
                        : "<p>No extracted fields were returned by the API.</p>"
                }

                <div class="review-actions">
                    <button id="accept-invoice" type="button">Accept</button>
                    <button id="correct-invoice" type="button">Save Corrections</button>
                    <button id="reject-invoice" type="button">Reject</button>
                </div>

                <p id="review-message" role="status"></p>
            </div>
        </div>
    `;

    $("#back-dashboard")?.addEventListener("click", showDashboard);

    $("#accept-invoice")?.addEventListener("click", () => {
        submitDecision("approve");
    });

    $("#correct-invoice")?.addEventListener("click", () => {
        submitDecision("correct");
    });

    $("#reject-invoice")?.addEventListener("click", () => {
        submitDecision("reject");
    });
}

// -------------------- SAVE REVIEW DECISION --------------------

async function submitDecision(decision) {
    if (!activeExtraction) return;

    const extractionId = getExtractionId(activeExtraction);

    if (!extractionId) {
        showMessage(
            "#review-message",
            "Extraction ID is missing. Reload the invoice and try again.",
            true
        );
        return;
    }

    const payload = { decision };

    if (decision === "correct") {
        const originalData = getInvoiceData(activeExtraction);
        const correctedData = {};

        try {
            document.querySelectorAll(".extracted-field-input")
                .forEach((input) => {
                    const key = input.dataset.field;
                    const raw = input.value.trim();
                    const original = originalData[key];

                    if (raw === "") {
                        correctedData[key] = null;
                    } else if (
                        typeof original === "number"
                    ) {
                        const number = Number(raw);

                        if (!Number.isFinite(number)) {
                            throw new Error(
                                `${key} must be a valid number.`
                            );
                        }

                        correctedData[key] = number;
                    } else if (
                        original !== null &&
                        typeof original === "object"
                    ) {
                        correctedData[key] = JSON.parse(raw);
                    } else {
                        correctedData[key] = raw;
                    }
                });

            payload.corrected_data = correctedData;
        } catch (error) {
            showMessage(
                "#review-message",
                `Invalid correction: ${error.message}`,
                true
            );
            return;
        }
    }

    try {
        await apiRequest(
            `/review/${encodeURIComponent(extractionId)}/decision`,
            {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            }
        );

        showMessage("#review-message", "Review saved successfully.");

        activeExtraction = null;

        await loadDashboard();

        const section = $("#document-review");

        if (section) {
            section.innerHTML = `
                <div class="main-empty">
                    <h2>Review saved</h2>
                    <p>Your invoice decision has been submitted.</p>
                </div>
            `;
        }
    } catch (error) {
        console.error("Review decision error:", error);

        showMessage(
            "#review-message",
            `Could not save decision: ${error.message}`,
            true
        );
    }
}

// -------------------- UPLOAD PDF --------------------

async function uploadInvoice() {
    const fileInput = $("#pdf-file");
    const uploadButton = $("#upload-btn");

    if (!fileInput?.files?.length) {
        showMessage("#upload-status", "Please select a PDF file.", true);
        return;
    }

    const file = fileInput.files[0];

    if (!file.name.toLowerCase().endsWith(".pdf")) {
        showMessage("#upload-status", "Please select a PDF file.", true);
        return;
    }

    const formData = new FormData();
    formData.append("file", file);

    if (uploadButton) uploadButton.disabled = true;

    showMessage("#upload-status", "Uploading and extracting invoice...");

    try {
        const result = await apiRequest("/documents/upload", {
            method: "POST",
            body: formData
        });

        showMessage("#upload-status", "Upload completed successfully.");

        fileInput.value = "";

        await loadDashboard();

        const documentId = getDocumentId(result);

        if (documentId) {
            await selectExtraction({ documentId });
        }
    } catch (error) {
        console.error("Upload error:", error);

        showMessage(
            "#upload-status",
            `Upload failed: ${error.message}`,
            true
        );
    } finally {
        if (uploadButton) uploadButton.disabled = false;
    }
}


document.addEventListener("DOMContentLoaded", () => {
    $("#upload-btn")?.addEventListener("click", uploadInvoice);
    $("#refresh-dashboard")?.addEventListener("click", loadDashboard);

    $("#invoice-search")?.addEventListener(
        "input",
        renderInvoiceHistory
    );

    loadDashboard();
});
