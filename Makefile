CXX      = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -O2 -pipe -I include
BINDIR   = bin

all: $(BINDIR)/line_gl $(BINDIR)/test_line_gl

$(BINDIR):
	mkdir -p $(BINDIR)

$(BINDIR)/line_gl: src/main.cpp | $(BINDIR)
	$(CXX) $(CXXFLAGS) -o $@ $<

$(BINDIR)/test_line_gl: src/test.cpp | $(BINDIR)
	$(CXX) $(CXXFLAGS) -o $@ $<

clean:
	rm -f $(BINDIR)/line_gl $(BINDIR)/test_line_gl
