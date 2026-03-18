## Công việc cần làm:
## Sửa lại logic các file .py trong folder extract_quiz để câu hỏi được insert vào database có mức độ khó 1, 2, 3 tương ứng với số câu hỏi ở mức độ khó tăng dần

## Sửa lại file quiz_generator.py để có thể tạo ra quiz dựa trên nội dung của từng lesson, tham số là chapter id, lesson id, số lượng câu hỏi, số câu hỏi ở mức độ khó 1, 2, 3 (tương ứng với số câu hỏi ở mức độ khó tăng dần)

* Sửa lại các file .py trong folder roadmap_gen để follow theo logic sau:
    * Roadmap được tạo với mụ đích giúp người dùng ôn tập lại các kiến thức đã học
    * Input là subject_id, total_time
    * Dựa vào nội dung các bài kiểm tra để giới hạn lại số chapter cần dùng để tạo roadmap
    * Output sẽ bao gồm nhiều node, mỗi node có:
        * chapter_id (1 chapter có thể có nhiều lesson)
            * lesson_id (mỗi lesson có một time riêng, một explain riêng do LLM tự ước lượng dựa trên kết quả các bài kiểm tra, xác định lesson_id bằng các câu hỏi học sinh làm sai trong bài kiểm tra, sử dụng embedding có sẵn để liên kết các câu hỏi với content_blocks, từ đó liên kết câu hỏi với lesson_id)
                * time (tính bằng giờ, dựa vào tổng thời gian mà người dùng nhập, phân bổ thời gian cho từng lesson dựa vào số lượng câu hỏi sai thuộc lesson đó, số lượng câu hỏi sai càng nhiều thì thời gian càng lâu)
                * explain (giải thích rằng tại sao cần phải ôn tập lesson này với khoảng thời gian này, dựa vào kết quả so sánh giữa đáp án mà học sinh chọn và đáp án đúng của câu hỏi mà học sinh làm sai để tìm ra lý do học sinh làm sai)
    * Tạo thêm một bảng trong db_roadmap.sql để lưu trữ thông tin của roadmap theo output như trên