1. hiện tại đang tạo các câu hỏi, các câu hỏi sẽ không bị trùng nhau trong một môn học, nhưng khi học sinh sử dụng hàm liên tục se tạo ra mọt loạt câu hỏi lý thuyết, tuy nhiên mỗi câu hỏi chỉ có giá trị sử dụng 1 lần vì thuật toán không cho lặp lại câu hỏi
VD: khi học sinh lựa chọn môn toán, chương đạo hàm, số lượng câu hỏi là 30, với 10 câu là được tạo bởi AI, thì AI sẽ tạo ra 10 câu hỏi lý thuyết mới, không trùng với các câu hỏi lý thuyết đang có trong ngân hàng câu hỏi (nên là mỗi học sinh se có một database riêng để dễ kiểm soát số lượng câu hỏi)

2. Roadmap:
- cần tạo thêm function để tổng hợp quiz tạo thành bài test cho học sinh
-> cần tạo thêm bảng để lưu test
-> cần tạo bảng để lưu kết quả bài test (lưu theo từng câu, làm đúng hay sai, mỗi câu có nội dung thuộc chương nào, mục nào, tiểu mục nào)
- roadmap dựa vào student_id, subject_id và kết quả bài test của học sinh tương ứng + thời gian ôn tập mà học sinh lựa chọn, liệt kê ra các chapter học sinh còn sai, từ đó đưa ra thời gian ôn tập phù hợp với từng chap (chap sai nhiều sẽ có thời gian ôn tập nhiều hơn)