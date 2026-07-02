# THL Maps License Lock Setup

## 1. Chuẩn bị Google Sheet

Sheet license cần tối thiểu các cột sau:

- `Mã Kích Hoạt`
- `Trạng Thái`
- `Khách hàng`

Apps Script sẽ tự tạo thêm các cột này nếu chưa có:

- `Machine ID`
- `Machine Display ID`
- `Activated At`
- `Last Seen At`
- `App Name`
- `App Version`

`Trạng Thái` phải là `active` thì license mới kích hoạt được.

## 2. Tạo Apps Script Web App

1. Mở [script.new](https://script.new) hoặc vào Apps Script.
2. Tạo project mới.
3. Mở file [license_apps_script_webapp.gs](/D:/THL_Tool/GG_Map_7.9_new/license_apps_script_webapp.gs) và dán toàn bộ nội dung vào Apps Script.
4. Sửa 2 giá trị trong `CONFIG`:

```javascript
SPREADSHEET_ID: '1cOR2RryFWtJLU7JD0Enlx1a7jj1ta8rgA0gQ4xDE5ro',
SHEET_NAME: 'License',
```

Mình đã điền sẵn `SPREADSHEET_ID` theo link Google Sheet anh cung cấp.

## 3. Deploy Web App

1. Chọn `Deploy` -> `New deployment`.
2. Loại deploy: `Web app`.
3. `Execute as`: chọn tài khoản của anh.
4. `Who has access`: chọn `Anyone`.
5. Deploy và copy URL kết thúc bằng `/exec`.

## 4. Gắn URL vào tool

Mở file [ui_cao_map_license_server.json](/D:/THL_Tool/GG_Map_7.9_new/Save_data/ui_cao_map_license_server.json) và điền:

```json
{
  "license_api_url": "https://script.google.com/macros/s/PASTE_WEB_APP_ID/exec"
}
```

## 5. Cách hoạt động sau khi xong

- Lần đầu nhập mã, app gọi Apps Script.
- Nếu `Machine ID` trên Sheet đang trống, Apps Script sẽ tự ghi `Machine ID` của máy hiện tại vào đúng dòng license đó.
- Nếu license đã gắn với máy khác, Apps Script trả về từ chối.
- Sau khi kích hoạt thành công, app lưu trạng thái local và lần sau mở tool sẽ không hỏi lại mã.

## 6. Gợi ý quản trị

- Khi muốn chuyển license sang máy mới: xóa giá trị cột `Machine ID` ở dòng license đó.
- Khi muốn khóa license: đổi `Trạng Thái` sang giá trị khác `active`.
- Nếu đổi tên sheet, nhớ cập nhật lại `SHEET_NAME` trong Apps Script.

## 7. Lưu ý bảo mật

Giải pháp Apps Script + client Python giúp khóa 1 máy thực tế cho vận hành thông thường, nhưng chưa phải mô hình chống reverse-engineering tuyệt đối. Nếu cần mức bảo vệ cao hơn, bước tiếp theo nên là ký license bằng chữ ký số hoặc dùng backend riêng.
