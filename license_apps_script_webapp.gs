const CONFIG = {
  SPREADSHEET_ID: '1cOR2RryFWtJLU7JD0Enlx1a7jj1ta8rgA0gQ4xDE5ro',
  SHEET_NAME: 'License',
  LOCK_TIMEOUT_MS: 15000,
};

const HEADER_ALIASES = {
  licenseKey: ['Mã Kích Hoạt', 'Ma Kich Hoat', 'License Key', 'License'],
  status: ['Trạng Thái', 'Trang Thai', 'Status'],
  customer: ['Khách hàng', 'Khach hang', 'Customer'],
  machineId: ['Machine ID', 'ID Máy', 'Id May', 'MachineID'],
  machineDisplayId: ['Machine Display ID', 'ID Máy Rút Gọn', 'Machine Short ID'],
  activatedAt: ['Activated At', 'Ngày Kích Hoạt', 'Ngay Kich Hoat'],
  lastSeenAt: ['Last Seen At', 'Lần Xác Thực Cuối', 'Lan Xac Thuc Cuoi'],
  appName: ['App Name', 'Tên Tool', 'Ten Tool'],
  appVersion: ['App Version', 'Phiên Bản', 'Phien Ban'],
};

function doGet(e) {
  return handleRequest_(e);
}

function doPost(e) {
  return handleRequest_(e);
}

function handleRequest_(e) {
  try {
    const payload = parsePayload_(e);
    const action = normalizeText_(payload.action || 'health');

    if (action === 'health') {
      return jsonResponse_({
        ok: true,
        code: 'healthy',
        message: 'License web app is ready.',
      });
    }

    if (action === 'activatelicense') {
      return jsonResponse_(activateLicense_(payload));
    }

    return jsonResponse_({
      ok: false,
      code: 'unsupported_action',
      message: 'Action không được hỗ trợ.',
    });
  } catch (error) {
    return jsonResponse_({
      ok: false,
      code: 'server_error',
      message: error && error.message ? error.message : 'Lỗi Apps Script không xác định.',
    });
  }
}

function activateLicense_(payload) {
  const licenseKey = cleanString_(payload.license_key);
  const machineId = cleanString_(payload.machine_id);
  const machineDisplayId = cleanString_(payload.machine_display_id);
  const appName = cleanString_(payload.app_name);
  const appVersion = cleanString_(payload.app_version);

  if (!licenseKey || !machineId) {
    return {
      ok: false,
      code: 'bad_request',
      message: 'Thiếu license_key hoặc machine_id.',
    };
  }

  const lock = LockService.getScriptLock();
  lock.waitLock(CONFIG.LOCK_TIMEOUT_MS);

  try {
    const sheet = getLicenseSheet_();
    ensureColumn_(sheet, HEADER_ALIASES.machineId, 'Machine ID');
    ensureColumn_(sheet, HEADER_ALIASES.machineDisplayId, 'Machine Display ID');
    ensureColumn_(sheet, HEADER_ALIASES.activatedAt, 'Activated At');
    ensureColumn_(sheet, HEADER_ALIASES.lastSeenAt, 'Last Seen At');
    ensureColumn_(sheet, HEADER_ALIASES.appName, 'App Name');
    ensureColumn_(sheet, HEADER_ALIASES.appVersion, 'App Version');

    const values = sheet.getDataRange().getDisplayValues();
    if (!values.length) {
      throw new Error('Sheet license đang trống.');
    }

    const headers = values[0];
    const keyColumn = resolveColumnIndex_(headers, HEADER_ALIASES.licenseKey);
    const statusColumn = resolveColumnIndex_(headers, HEADER_ALIASES.status);
    const customerColumn = resolveColumnIndex_(headers, HEADER_ALIASES.customer);
    const machineColumn = resolveColumnIndex_(headers, HEADER_ALIASES.machineId);
    const machineDisplayColumn = resolveColumnIndex_(headers, HEADER_ALIASES.machineDisplayId);
    const activatedAtColumn = resolveColumnIndex_(headers, HEADER_ALIASES.activatedAt);
    const lastSeenAtColumn = resolveColumnIndex_(headers, HEADER_ALIASES.lastSeenAt);
    const appNameColumn = resolveColumnIndex_(headers, HEADER_ALIASES.appName);
    const appVersionColumn = resolveColumnIndex_(headers, HEADER_ALIASES.appVersion);

    if (!keyColumn || !statusColumn) {
      throw new Error('Sheet thiếu cột Mã Kích Hoạt hoặc Trạng Thái.');
    }

    const targetKey = cleanString_(licenseKey);
    let targetRow = 0;
    for (let rowIndex = 2; rowIndex <= values.length; rowIndex += 1) {
      const rowKey = cleanString_(values[rowIndex - 1][keyColumn - 1]);
      if (rowKey === targetKey) {
        targetRow = rowIndex;
        break;
      }
    }

    if (!targetRow) {
      return {
        ok: false,
        code: 'license_not_found',
        message: 'Mã kích hoạt không hợp lệ.',
      };
    }

    const rowValues = values[targetRow - 1];
    const status = cleanString_(rowValues[statusColumn - 1]).toLowerCase();
    const customerName = customerColumn ? cleanString_(rowValues[customerColumn - 1]) : '';
    const storedMachineId = machineColumn ? cleanString_(rowValues[machineColumn - 1]) : '';

    if (status !== 'active') {
      return {
        ok: false,
        code: 'inactive_license',
        message: 'Mã kích hoạt này đã bị khóa hoặc hết hạn.',
        status: status,
      };
    }

    if (storedMachineId && normalizeText_(storedMachineId) !== normalizeText_(machineId)) {
      return {
        ok: false,
        code: 'machine_locked',
        message: 'Mã kích hoạt này đã được gán cho một máy khác.',
        status: status,
        customer_name: customerName,
        machine_id: storedMachineId,
      };
    }

    const now = new Date();

    if (!storedMachineId) {
      sheet.getRange(targetRow, machineColumn).setValue(machineId);
      sheet.getRange(targetRow, activatedAtColumn).setValue(now);
    }

    sheet.getRange(targetRow, machineDisplayColumn).setValue(machineDisplayId);
    sheet.getRange(targetRow, lastSeenAtColumn).setValue(now);

    if (appName) {
      sheet.getRange(targetRow, appNameColumn).setValue(appName);
    }
    if (appVersion) {
      sheet.getRange(targetRow, appVersionColumn).setValue(appVersion);
    }

    return {
      ok: true,
      code: storedMachineId ? 'already_activated' : 'activated',
      message: storedMachineId
        ? 'License đã được xác thực trên đúng máy này.'
        : 'Kích hoạt thành công và đã khóa vào máy hiện tại.',
      status: status,
      customer_name: customerName,
      machine_id: storedMachineId || machineId,
    };
  } finally {
    lock.releaseLock();
  }
}

function getLicenseSheet_() {
  if (!CONFIG.SPREADSHEET_ID || CONFIG.SPREADSHEET_ID === 'PUT_YOUR_SPREADSHEET_ID_HERE') {
    throw new Error('Hãy cập nhật CONFIG.SPREADSHEET_ID trong Apps Script.');
  }

  const spreadsheet = SpreadsheetApp.openById(CONFIG.SPREADSHEET_ID);
  if (!CONFIG.SHEET_NAME) {
    return spreadsheet.getSheets()[0];
  }

  const sheet = spreadsheet.getSheetByName(CONFIG.SHEET_NAME);
  if (!sheet) {
    throw new Error(`Không tìm thấy sheet "${CONFIG.SHEET_NAME}".`);
  }
  return sheet;
}

function ensureColumn_(sheet, aliases, columnName) {
  const headers = sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), 1)).getDisplayValues()[0];
  const foundIndex = resolveColumnIndex_(headers, aliases);
  if (foundIndex) {
    return foundIndex;
  }

  const nextColumn = Math.max(sheet.getLastColumn(), 1) + 1;
  sheet.getRange(1, nextColumn).setValue(columnName);
  return nextColumn;
}

function resolveColumnIndex_(headers, aliases) {
  const normalizedHeaders = headers.map(normalizeText_);
  for (let i = 0; i < aliases.length; i += 1) {
    const alias = normalizeText_(aliases[i]);
    const columnIndex = normalizedHeaders.indexOf(alias);
    if (columnIndex !== -1) {
      return columnIndex + 1;
    }
  }
  return 0;
}

function parsePayload_(e) {
  if (e && e.postData && e.postData.contents) {
    return JSON.parse(e.postData.contents);
  }
  if (e && e.parameter) {
    return e.parameter;
  }
  return {};
}

function cleanString_(value) {
  return value === null || value === undefined ? '' : String(value).trim();
}

function normalizeText_(value) {
  return cleanString_(value)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '');
}

function jsonResponse_(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload)).setMimeType(ContentService.MimeType.JSON);
}
