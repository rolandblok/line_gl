CXX      = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -O2 -pipe -I include -MMD -MP
BINDIR   = bin

all: $(BINDIR)/line_gl 

$(BINDIR):
	mkdir -p $(BINDIR)

$(BINDIR)/line_gl: src/main.cpp | $(BINDIR)
	$(CXX) $(CXXFLAGS) -MF $(BINDIR)/line_gl.d -o $@ $<

-include $(BINDIR)/line_gl.d $(BINDIR)/test_line_gl.d

clean:
	rm -f $(BINDIR)/line_gl  $(BINDIR)/*.d
