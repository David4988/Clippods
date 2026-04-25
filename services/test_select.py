from segment_selection import select_segments

# Case 1: Empty timestamps (fallback)
print("TEST 1: Empty input")
result = select_segments([], 10)
print(result)

# Case 2: Normal timestamps
timestamps = [
    {"start": 0, "end": 5, "text": "hello world"},
    {"start": 10, "end": 20, "text": "this is a longer sentence"},
    {"start": 30, "end": 50, "text": "another segment here"},
]

print("\nTEST 2: Normal input")
result = select_segments(timestamps, 120)
print(result)